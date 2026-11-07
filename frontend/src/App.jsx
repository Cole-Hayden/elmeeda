import './App.css'
import BookingList from './BookingList.jsx'
import ToolLog from './ToolLog.jsx'
import { useRealtimeCall } from './useRealtimeCall.js'
import VoiceCall from './VoiceCall.jsx'

function App() {
  const call = useRealtimeCall()

  return (
    <div className="issue-page">
      <main>
        <h1>Voice Booking Agent</h1>
        <VoiceCall call={call} />
        <BookingList refreshKey={call.booking?.bookingId} />
      </main>
      <aside className="tool-panel">
        <ToolLog entries={call.toolLog} />
      </aside>
    </div>
  )
}

export default App
