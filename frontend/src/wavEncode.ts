/**
 * Convert an audio/video file the browser can decode (m4a, mp3, mp4, ...)
 * into the mono 16-bit PCM WAV at 24 kHz the transcription model requires.
 *
 * This removes the server's ffmpeg dependency for uploads: Chrome and Edge
 * decode AAC/m4a locally. Throws when the browser cannot decode the file;
 * callers fall back to uploading the original (the backend then needs
 * ffmpeg) so no path regresses.
 */
const TARGET_SAMPLE_RATE = 24000

export async function fileToWavBlob(file: File): Promise<Blob> {
  const arrayBuffer = await file.arrayBuffer()
  const AudioContextCtor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioContextCtor) throw new Error('Web Audio is not available in this browser.')
  const context = new AudioContextCtor()
  try {
    // decodeAudioData detaches the buffer; hand it a copy.
    const decoded = await context.decodeAudioData(arrayBuffer.slice(0))
    const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_SAMPLE_RATE))
    const offline = new OfflineAudioContext(1, frames, TARGET_SAMPLE_RATE)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    const rendered = await offline.startRendering()
    return encodeWavPcm16(rendered.getChannelData(0), TARGET_SAMPLE_RATE)
  } finally {
    void context.close().catch(() => undefined)
  }
}

function encodeWavPcm16(samples: Float32Array, sampleRate: number): Blob {
  const bytes = 44 + samples.length * 2
  const buffer = new ArrayBuffer(bytes)
  const view = new DataView(buffer)
  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeAscii(0, 'RIFF')
  view.setUint32(4, bytes - 8, true)
  writeAscii(8, 'WAVE')
  writeAscii(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeAscii(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let offset = 44
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}
