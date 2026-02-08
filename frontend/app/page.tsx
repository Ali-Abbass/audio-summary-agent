'use client';

import { useEffect, useRef, useState } from 'react';

type Mode = 'now' | 'schedule';

type Summary = {
  bullets: string[];
  next_step: string;
};

type RequestStatus = {
  request_id: string;
  status: 'pending' | 'processing' | 'sent' | 'failed';
  attempts: number;
  last_error: string | null;
  summary: Summary | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

async function parseApiError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.error?.message || `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export default function HomePage() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [mode, setMode] = useState<Mode>('now');
  const [scheduledAt, setScheduledAt] = useState('');
  const [requestId, setRequestId] = useState<string | null>(null);
  const [requestStatus, setRequestStatus] = useState<RequestStatus | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, [audioUrl]);

  useEffect(() => {
    if (!requestId) {
      return;
    }

    let cancelled = false;
    let intervalId: NodeJS.Timeout | null = null;

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/requests/${requestId}`);
        if (!res.ok) {
          throw new Error(await parseApiError(res));
        }
        const data = (await res.json()) as RequestStatus;
        if (!cancelled) {
          setRequestStatus(data);
          if (data.status === 'sent') {
            setMessage('Summary email sent successfully.');
          }
          if (data.status === 'sent' || data.status === 'failed') {
            if (intervalId) {
              clearInterval(intervalId);
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Status polling failed.');
        }
      }
    };

    poll().catch(() => undefined);
    intervalId = setInterval(() => {
      poll().catch(() => undefined);
    }, 3000);

    return () => {
      cancelled = true;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [requestId]);

  const startRecording = async () => {
    setError(null);
    setMessage(null);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError('This browser does not support microphone recording.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const recorder = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
        : new MediaRecorder(stream);

      chunksRef.current = [];
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        setAudioBlob(blob);
        if (audioUrl) {
          URL.revokeObjectURL(audioUrl);
        }
        setAudioUrl(URL.createObjectURL(blob));
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not access microphone.');
    }
  };

  const stopRecording = () => {
    if (!mediaRecorderRef.current) {
      return;
    }
    mediaRecorderRef.current.stop();
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    setIsRecording(false);
  };

  const submit = async () => {
    setError(null);
    setMessage(null);
    setRequestStatus(null);

    if (!audioBlob) {
      setError('Please record audio before submitting.');
      return;
    }
    if (!email.trim()) {
      setError('Please enter your email address.');
      return;
    }

    let sendAt: string | null = null;
    if (mode === 'schedule') {
      if (!scheduledAt) {
        setError('Please select a schedule time.');
        return;
      }
      sendAt = new Date(scheduledAt).toISOString();
    }

    setIsSubmitting(true);
    try {
      const extension = audioBlob.type.includes('ogg')
        ? 'ogg'
        : audioBlob.type.includes('wav')
          ? 'wav'
          : audioBlob.type.includes('mpeg')
            ? 'mp3'
            : 'webm';

      const formData = new FormData();
      formData.append('file', audioBlob, `recording.${extension}`);

      const uploadRes = await fetch(`${API_BASE}/v1/audio`, {
        method: 'POST',
        body: formData,
      });
      if (!uploadRes.ok) {
        throw new Error(await parseApiError(uploadRes));
      }
      const uploadData = (await uploadRes.json()) as { audio_id: string };

      const requestRes = await fetch(`${API_BASE}/v1/requests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          audio_id: uploadData.audio_id,
          send_at: sendAt,
        }),
      });
      if (!requestRes.ok) {
        throw new Error(await parseApiError(requestRes));
      }

      const requestData = (await requestRes.json()) as { request_id: string; status: string };
      setRequestId(requestData.request_id);
      setMessage('Request submitted. Status will update automatically.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main>
      <section className="panel">
        <h1>Voice Summary Agent</h1>
        <p>Record a short voice note, then send immediately or schedule delivery.</p>

        <div className="controls">
          <div className="row two">
            <button type="button" onClick={isRecording ? stopRecording : startRecording}>
              {isRecording ? 'Stop Recording' : 'Start Recording'}
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => {
                setAudioBlob(null);
                if (audioUrl) {
                  URL.revokeObjectURL(audioUrl);
                  setAudioUrl(null);
                }
              }}
              disabled={!audioBlob || isSubmitting}
            >
              Clear Recording
            </button>
          </div>

          {audioUrl && (
            <div className="row">
              <label htmlFor="playback">Preview</label>
              <audio id="playback" controls src={audioUrl} />
            </div>
          )}

          <div className="row">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </div>

          <div className="row two">
            <div>
              <label htmlFor="mode">Delivery Mode</label>
              <select id="mode" value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
                <option value="now">Send now</option>
                <option value="schedule">Schedule</option>
              </select>
            </div>
            {mode === 'schedule' && (
              <div>
                <label htmlFor="scheduleAt">Send at</label>
                <input
                  id="scheduleAt"
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(event) => setScheduledAt(event.target.value)}
                />
              </div>
            )}
          </div>

          <button type="button" onClick={submit} disabled={isSubmitting || isRecording || !audioBlob}>
            {isSubmitting ? 'Submitting...' : 'Submit'}
          </button>
        </div>

        {(message || error || requestStatus) && (
          <div className="status-box">
            {message && <p className="success">{message}</p>}
            {error && <p className="error">{error}</p>}

            {requestStatus && (
              <>
                <p>
                  <strong>Request:</strong> {requestStatus.request_id}
                </p>
                <p>
                  <strong>Status:</strong> {requestStatus.status}
                </p>
                <p>
                  <strong>Attempts:</strong> {requestStatus.attempts}
                </p>
                {requestStatus.last_error && (
                  <p>
                    <strong>Last error:</strong> {requestStatus.last_error}
                  </p>
                )}
                {requestStatus.summary && (
                  <>
                    <p>
                      <strong>Summary</strong>
                    </p>
                    <ul>
                      {requestStatus.summary.bullets.map((bullet, index) => (
                        <li key={`${bullet}-${index}`}>{bullet}</li>
                      ))}
                    </ul>
                    <p>
                      <strong>Next step:</strong> {requestStatus.summary.next_step}
                    </p>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
