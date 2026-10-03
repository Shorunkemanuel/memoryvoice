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

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)
  const transcriptionInProgressRef = useRef(false)

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
      const response = await fetch('/api/memories/audio', {
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
      const response = await fetch('/api/memories/transcribe', {
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
      const response = await fetch('/api/memories', {
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
    } catch (err: unknown) {
      setMemoryError(
        err instanceof Error ? err.message : 'Failed to create memory. Please try again.',
      )
    } finally {
      setIsCreatingMemory(false)
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

          <button
            className="btn btn-secondary"
            onClick={() => console.log('View clicked')}
            type="button"
            aria-label="View saved memories (currently disabled)"
          >
            View memories
          </button>
        </div>
      </section>
    </main>
  )
}
