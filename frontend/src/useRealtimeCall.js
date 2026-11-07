import { useCallback, useEffect, useRef, useState } from 'react'
import { createToolRelay, forModel, updateLog } from './toolRelay.js'

const TOOL_TIMEOUT_MS = 10000

async function postToCall(issueId, path, body) {
  try {
    const res = await fetch(`/api/voice/calls/${issueId}/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TOOL_TIMEOUT_MS),
    })
    if (!res.ok) return { error: 'tool_failed', status: res.status }
    return await res.json()
  } catch {
    // The model never gets an answer unless a result is always returned.
    return { error: 'tool_failed' }
  }
}

export function useRealtimeCall() {
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [issueId, setIssueId] = useState(null)
  const [missing, setMissing] = useState([])
  const [search, setSearch] = useState(null)
  const [prepared, setPrepared] = useState(null)
  const [booking, setBooking] = useState(null)
  const [toolLog, setToolLog] = useState([])
  const call = useRef(null)

  const stop = useCallback(() => {
    if (!call.current) return
    const { peer, mic, audio } = call.current
    call.current = null
    peer.close()
    mic.getTracks().forEach((track) => track.stop())
    audio.srcObject = null
    setStatus('idle')
  }, [])

  useEffect(() => stop, [stop])

  const start = useCallback(async () => {
    if (call.current) return
    setStatus('connecting')
    setError(null)
    setMissing([])
    setSearch(null)
    setPrepared(null)
    setBooking(null)
    setIssueId(null)
    setToolLog([])

    let mic
    let peer
    try {
      mic = await navigator.mediaDevices.getUserMedia({ audio: true })
      peer = new RTCPeerConnection()
      const audio = new Audio()
      audio.autoplay = true
      peer.ontrack = (event) => {
        audio.srcObject = event.streams[0]
      }
      mic.getTracks().forEach((track) => peer.addTrack(track, mic))

      const session = { peer, mic, audio, issueId: null }
      call.current = session
      const events = peer.createDataChannel('oai-events')

      const send = (event) => events.send(JSON.stringify(event))

      const relay = createToolRelay({
        post: (path, body) => postToCall(session.issueId, path, body),
        onLog: (entry) => setToolLog((log) => updateLog(log, entry)),
      })

      // The screen only ever shows what a tool returned, not what the agent says happened.
      const showResult = (name, result) => {
        if (result.bookingId) {
          setBooking(result)
          setPrepared(null)
          return
        }
        if (name === 'book_repair') setPrepared(null)
        if (name === 'prepare_booking') setPrepared(result.error ? null : result)
        if (name === 'search_shops' && !result.error) {
          setSearch(result)
          setPrepared(null)
          if (result.existingBooking) setBooking(result.existingBooking)
        }
        if (name === 'update_issue' && result.missingDetails) setMissing(result.missingDetails)
      }

      const handleResponseDone = async (response) => {
        // Interrupted responses don't complete, so their tool calls never run.
        if (response.status !== 'completed') return
        const calls = response.output.filter((item) => item.type === 'function_call')
        if (calls.length === 0) return
        for (const item of calls) {
          const result = await relay.run(item.name, item.arguments)
          if (call.current !== session) return
          showResult(item.name, result)
          send({
            type: 'conversation.item.create',
            item: {
              type: 'function_call_output',
              call_id: item.call_id,
              output: JSON.stringify(forModel(result)),
            },
          })
          relay.delivered(item.name, result)
        }
        send({ type: 'response.create' })
      }

      events.onmessage = ({ data }) => {
        const event = JSON.parse(data)
        switch (event.type) {
          case 'input_audio_buffer.speech_started':
            relay.speechStarted(event.item_id)
            break
          case 'conversation.item.input_audio_transcription.completed':
            relay.transcribed(event.item_id, event.transcript)
            break
          case 'conversation.item.input_audio_transcription.failed':
            relay.transcriptionFailed(event.item_id)
            break
          case 'response.output_audio_transcript.done':
            relay.agentSaid(event.response_id, event.transcript)
            break
          case 'output_audio_buffer.stopped':
            relay.playbackStopped(event.response_id)
            break
          case 'output_audio_buffer.cleared':
            relay.playbackCleared(event.response_id)
            break
          case 'response.done':
            handleResponseDone(event.response)
            break
          case 'error':
            setError(event.error?.message ?? 'The voice service reported an error.')
            break
        }
      }
      events.onopen = () => setStatus('live')
      events.onclose = () => {
        if (call.current === session) stop()
      }

      const offer = await peer.createOffer()
      await peer.setLocalDescription(offer)
      const res = await fetch('/api/voice/calls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: offer.sdp,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Request failed with status ${res.status}`)
      }
      const { issueId: createdIssueId, sdp } = await res.json()
      session.issueId = createdIssueId
      setIssueId(createdIssueId)
      await peer.setRemoteDescription({ type: 'answer', sdp })
    } catch (err) {
      setError(err.message)
      if (call.current) {
        stop()
      } else {
        peer?.close()
        mic?.getTracks().forEach((track) => track.stop())
        setStatus('idle')
      }
    }
  }, [stop])

  return {
    status,
    error,
    issueId,
    missing,
    search,
    prepared,
    booking,
    toolLog,
    start,
    stop,
  }
}
