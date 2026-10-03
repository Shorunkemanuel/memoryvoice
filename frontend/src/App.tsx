import { useState, useRef, useEffect } from 'react'

type RecordingStatus = 'idle' | 'recording' | 'recorded' | 'uploading' | 'uploaded' | 'error'

type StructuredMemory = {
  title: string
  people: string[]
  places: string[]
  dates: string[]
  events: string[]
  details: string[]
}

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

const isStructuredMemory = (value: unknown): value is StructuredMemory => {
  if (!value || typeof value !== 'object') return false
  const memory = value as Record<string, unknown>
  return (
    typeof memory.title === 'string' &&
    ['people', 'places', 'dates', 'events', 'details'].every(
      (field) => Array.isArray(memory[field]) && memory[field].every((item) => typeof item === 'string'),
    )
  )
}

export default function App() {
  const [status, setStatus] = useState<RecordingStatus>('idle')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [duration, setDuration] = useState<number>(0)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [transcriptionError, setTranscriptionError] = useState('')
  const [transcript, setTranscript] = useState('')
  const [isCreatingMemory, setIsCreatingMemory] = useState(false)
  const [memoryError, setMemoryError] = useState('')
  const [memory, setMemory] = useState<StructuredMemory | null>(null)
  const [savedMemories, setSavedMemories] = useState<StructuredMemory[]>([])
  const [isLoadingMemories, setIsLoadingMemories] = useState(false)
  const [memoriesError, setMemoriesError] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [askError, setAskError] = useState('')
  const [isAsking, setIsAsking] = useState(false)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)
  const transcriptionInProgressRef = useRef(false)
  const askingInProgressRef = useRef(false)

  const loadMemories = async () => {
    setIsLoadingMemories(true)
    setMemoriesError('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/memories`)
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.detail || `Unable to load memories (status ${response.status}).`)
      }
      if (!Array.isArray(data.memories) || !data.memories.every(isStructuredMemory)) {
        throw new Error('The server returned an invalid memory list.')
      }
      setSavedMemories(data.memories)
    } catch (err: unknown) {
      setMemoriesError(
        err instanceof Error ? err.message : 'Unable to load memories. Please try again.',
      )
    } finally {
      setIsLoadingMemories(false)
    }
  }

  useEffect(() => {
    void loadMemories()
  }, [])

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl)
      }
      if (timerRef.current) {
        window.clearInterval(timerRef.current)
      }
    }
  }, [audioUrl])

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  const startRecording = async () => {
    setErrorMessage('')
    setUploadedFilename(null)
    audioChunksRef.current = []

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus('error')
      setErrorMessage('Audio recording is not supported in your browser.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        const mimeType = mediaRecorder.mimeType || 'audio/webm'
        const blob = new Blob(audioChunksRef.current, { type: mimeType })
        setAudioBlob(blob)
        const url = URL.createObjectURL(blob)
        setAudioUrl(url)
        setStatus('recorded')

        stream.getTracks().forEach((track) => track.stop())
      }

      mediaRecorder.start()
      setStatus('recording')
      setDuration(0)

      timerRef.current = window.setInterval(() => {
        setDuration((prev) => prev + 1)
      }, 1000)
    } catch (err: any) {
      setStatus('error')
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setErrorMessage('Microphone permission was denied. Please allow microphone access to record stories.')
      } else {
        setErrorMessage(`Could not start recording: ${err.message || 'Unknown error'}`)
      }
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && status === 'recording') {
      mediaRecorderRef.current.stop()
      if (timerRef.current) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }

  const uploadRecording = async () => {
    if (!audioBlob) return

    setStatus('uploading')
    setErrorMessage('')
    setTranscriptionError('')
    setTranscript('')

    const formData = new FormData()
    formData.append('file', audioBlob, 'memory-story.webm')

    try {
      const response = await fetch(`${API_BASE_URL}/api/memories/audio`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Upload failed with status ${response.status}`)
      }

      const data = await response.json()
      setUploadedFilename(data.filename)
      setStatus('uploaded')
    } catch (err: any) {
      setStatus('error')
      setErrorMessage(err.message || 'Failed to upload recording.')
    }
  }

  const transcribeRecording = async () => {
    if (!audioBlob || transcriptionInProgressRef.current) return

    transcriptionInProgressRef.current = true
    setIsTranscribing(true)
    setTranscriptionError('')
    setTranscript('')

    const formData = new FormData()
    formData.append('file', audioBlob, 'memory-story.webm')

    try {
      const response = await fetch(`${API_BASE_URL}/api/memories/transcribe`, {
        method: 'POST',
        body: formData,
      })
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || `Transcription failed with status ${response.status}`)
      }

      if (typeof data.transcript !== 'string' || !data.transcript.trim()) {
        throw new Error('The transcription response did not include a transcript. Please try again.')
      }

      setTranscript(data.transcript)
    } catch (err: unknown) {
      setTranscriptionError(
        err instanceof Error ? err.message : 'Failed to transcribe recording. Please try again.',
      )
    } finally {
      transcriptionInProgressRef.current = false
      setIsTranscribing(false)
    }
  }

  const createMemory = async () => {
    if (!transcript || isCreatingMemory) return

    setIsCreatingMemory(true)
    setMemoryError('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/memories`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ transcript }),
      })

      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to create memory.')
      }

      if (!data.memory || typeof data.memory !== 'object') {
        throw new Error('The server did not return a valid memory.')
      }

      setMemory(data.memory)
      await loadMemories()
    } catch (err: unknown) {
      setMemoryError(
        err instanceof Error ? err.message : 'Failed to create memory. Please try again.',
      )
    } finally {
      setIsCreatingMemory(false)
    }
  }

  const askMemory = async () => {
    if (!question.trim() || askingInProgressRef.current) return

    askingInProgressRef.current = true
    setIsAsking(true)
    setAnswer('')
    setAskError('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/memories/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.detail || `Unable to answer question (status ${response.status}).`)
      }
      if (typeof data.answer !== 'string' || !data.answer.trim()) {
        throw new Error('The server did not return an answer.')
      }
      setAnswer(data.answer)
    } catch (err: unknown) {
      setAskError(err instanceof Error ? err.message : 'Unable to answer. Please try again.')
    } finally {
      askingInProgressRef.current = false
      setIsAsking(false)
    }
  }

  const resetRecording = () => {
    if (transcriptionInProgressRef.current) return
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
    }
    setAudioBlob(null)
    setAudioUrl(null)
    setUploadedFilename(null)
    setDuration(0)
    setErrorMessage('')
    setTranscriptionError('')
    setTranscript('')
    setMemory(null)
    setMemoryError('')
    setIsTranscribing(false)
    transcriptionInProgressRef.current = false
    setStatus('idle')
  }

  return (
    <main className="container" role="main">
      <header>
        <h1>MemoryVoice</h1>
        <p className="tagline">Turn the stories you tell into memories you can keep.</p>
      </header>

      <section className="recorder-section" aria-label="Audio Recorder">
        {status === 'idle' && (
          <p className="status-message" aria-live="polite">Ready to record your memory.</p>
        )}
        {status === 'recording' && (
          <div className="recording-active" aria-live="polite">
            <span className="pulse-indicator" aria-hidden="true" />
            <p className="status-message">Recording in progress... ({formatTime(duration)})</p>
          </div>
        )}
        {status === 'recorded' && (
          <p className="status-message" aria-live="polite">Recording captured successfully. Listen to preview or upload below.</p>
        )}
        {status === 'uploading' && (
          <p className="status-message" aria-live="polite">Uploading your memory...</p>
        )}
        {status === 'uploaded' && (
          <div className="success-box" aria-live="polite">
            <p className="status-message success">Memory successfully uploaded!</p>
            {uploadedFilename && <p className="filename-info">Stored as: {uploadedFilename}</p>}
          </div>
        )}
        {status === 'error' && (
          <p className="status-message error" aria-live="assertive">{errorMessage}</p>
        )}
        {isTranscribing && (
          <p className="status-message" role="status" aria-live="polite" aria-busy="true">
            Transcribing your memory...
          </p>
        )}
        {transcriptionError && (
          <p className="status-message error" role="alert">{transcriptionError}</p>
        )}
        {transcript && (
          <section className="transcript-box" aria-labelledby="transcript-heading">
            <h2 id="transcript-heading">Transcript</h2>
            <p>{transcript}</p>
          </section>
        )}

        {memoryError && (
          <p className="status-message error" role="alert">{memoryError}</p>
        )}

        {transcript && !memory && (
          <button
            className="btn"
            onClick={createMemory}
            type="button"
            disabled={isCreatingMemory}
            aria-live="polite"
            aria-busy={isCreatingMemory}
          >
            {isCreatingMemory ? 'Creating memory...' : 'Create Memory'}
          </button>
        )}

        {memory && (
          <section className="memory-card" aria-labelledby="memory-heading">
            <h2 id="memory-heading">{memory.title || 'Memory'}</h2>
            <div className="memory-fields">
              <div>
                <h3>People</h3>
                <ul>{memory.people.length ? memory.people.map((person) => <li key={person}>{person}</li>) : <li>None</li>}</ul>
              </div>
              <div>
                <h3>Places</h3>
                <ul>{memory.places.length ? memory.places.map((place) => <li key={place}>{place}</li>) : <li>None</li>}</ul>
              </div>
              <div>
                <h3>Dates</h3>
                <ul>{memory.dates.length ? memory.dates.map((date) => <li key={date}>{date}</li>) : <li>None</li>}</ul>
              </div>
              <div>
                <h3>Events</h3>
                <ul>{memory.events.length ? memory.events.map((event) => <li key={event}>{event}</li>) : <li>None</li>}</ul>
              </div>
              <div>
                <h3>Details</h3>
                <ul>{memory.details.length ? memory.details.map((detail) => <li key={detail}>{detail}</li>) : <li>None</li>}</ul>
              </div>
            </div>
          </section>
        )}

        {audioUrl && (status === 'recorded' || status === 'uploading' || status === 'uploaded') && (
          <div className="audio-preview">
            <audio controls src={audioUrl} aria-label="Recorded audio playback preview">
              Your browser does not support the audio element.
            </audio>
          </div>
        )}

        <div className="button-group">
          {status === 'idle' && (
            <button
              className="btn"
              onClick={startRecording}
              type="button"
              aria-label="Start recording a memory"
            >
              Record a memory
            </button>
          )}

          {status === 'recording' && (
            <button
              className="btn btn-danger"
              onClick={stopRecording}
              type="button"
              aria-label="Stop recording"
            >
              Stop recording
            </button>
          )}

          {(status === 'recorded' || status === 'error') && audioBlob && (
            <button
              className="btn"
              onClick={uploadRecording}
              type="button"
              aria-label="Upload recording"
            >
              Upload recording
            </button>
          )}

          {status === 'uploaded' && !transcript && (
            <button
              className="btn"
              onClick={transcribeRecording}
              type="button"
              disabled={isTranscribing}
              aria-label={transcriptionError ? 'Retry transcription' : 'Transcribe recording'}
            >
              {isTranscribing ? 'Transcribing...' : transcriptionError ? 'Retry transcription' : 'Transcribe'}
            </button>
          )}

          {(status === 'recorded' || status === 'uploaded' || status === 'error') && (
            <button
              className="btn btn-secondary"
              onClick={resetRecording}
              type="button"
              disabled={isTranscribing}
              aria-label="Record another memory"
            >
              Record another
            </button>
          )}

          <button className="btn btn-secondary" onClick={() => document.getElementById('memory-library')?.scrollIntoView({ behavior: 'smooth' })} type="button">
            View memories
          </button>
        </div>
      </section>

      <section className="library-section" id="memory-library" aria-labelledby="memory-library-heading">
        <h2 id="memory-library-heading">Memory Library</h2>
        {isLoadingMemories && <p className="status-message" role="status" aria-live="polite">Loading saved memories...</p>}
        {memoriesError && (
          <div className="library-error">
            <p className="status-message error" role="alert">{memoriesError}</p>
            <button className="btn btn-secondary" onClick={() => void loadMemories()} type="button" disabled={isLoadingMemories}>
              Retry
            </button>
          </div>
        )}
        {!isLoadingMemories && !memoriesError && savedMemories.length === 0 && (
          <p className="status-message">No saved memories yet. Create a memory to see it here.</p>
        )}
        {savedMemories.length > 0 && (
          <div className="memory-library-list">
            {savedMemories.map((savedMemory, index) => (
              <article className="memory-card" key={`${savedMemory.title}-${index}`}>
                <h3>{savedMemory.title || 'Memory'}</h3>
                <div className="memory-fields">
                  {([
                    ['People', savedMemory.people],
                    ['Places', savedMemory.places],
                    ['Dates', savedMemory.dates],
                    ['Events', savedMemory.events],
                    ['Details', savedMemory.details],
                  ] as const).map(([label, items]) => items.length > 0 && (
                    <div key={label}>
                      <h4>{label}</h4>
                      <ul>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{item}</li>)}</ul>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="ask-section" aria-labelledby="ask-memories-heading">
        <h2 id="ask-memories-heading">Ask Your Memories</h2>
        <form onSubmit={(event) => { event.preventDefault(); void askMemory() }}>
          <label htmlFor="memory-question">Ask your memories</label>
          <textarea
            id="memory-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What did I tell you about my grandmother?"
            rows={3}
            disabled={isAsking}
          />
          <button className="btn" type="submit" disabled={isAsking || !question.trim()} aria-busy={isAsking}>
            {isAsking ? 'Asking...' : 'Ask'}
          </button>
        </form>
        {isAsking && <p className="status-message" role="status" aria-live="polite">Searching your saved memories...</p>}
        {askError && <p className="status-message error" role="alert">{askError}</p>}
        {answer && (
          <div className="answer-box" aria-labelledby="memory-answer-heading">
            <h3 id="memory-answer-heading">Answer</h3>
            <p aria-live="polite">{answer}</p>
          </div>
        )}
      </section>
    </main>
  )
}
