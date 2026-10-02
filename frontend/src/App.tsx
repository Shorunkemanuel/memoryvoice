export default function App() {
  return (
    <main className="container">
      <header>
        <h1>MemoryVoice</h1>
        <p className="tagline">Turn the stories you tell into memories you can keep.</p>
      </header>
      <div className="button-group">
        <button
          className="btn"
          onClick={() => console.log('Record clicked')}
          type="button"
        >
          Record a memory
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => console.log('View clicked')}
          type="button"
        >
          View memories
        </button>
      </div>
    </main>
  )
}
