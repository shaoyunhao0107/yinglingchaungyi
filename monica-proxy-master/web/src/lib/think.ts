// Reasoning models route their chain-of-thought through monica-proxy wrapped in
// <think>...</think> tags (see internal/monica/sse.go). We split a message into
// ordered "think" and "text" segments so the UI can render thinking collapsibly.
// The closing tag may be missing while a response is still streaming.

export type SegmentType = 'text' | 'think'

export interface Segment {
  type: SegmentType
  content: string
}

const OPEN = '<think>'
const CLOSE = '</think>'

export function splitThink(input: string): Segment[] {
  const segments: Segment[] = []
  let i = 0

  while (i < input.length) {
    const start = input.indexOf(OPEN, i)
    if (start === -1) {
      segments.push({ type: 'text', content: input.slice(i) })
      break
    }
    if (start > i) {
      segments.push({ type: 'text', content: input.slice(i, start) })
    }
    const afterOpen = start + OPEN.length
    const end = input.indexOf(CLOSE, afterOpen)
    if (end === -1) {
      // Unclosed tag: everything left is still-streaming thinking.
      segments.push({ type: 'think', content: input.slice(afterOpen) })
      break
    }
    segments.push({ type: 'think', content: input.slice(afterOpen, end) })
    i = end + CLOSE.length
  }

  return segments.filter((s) => s.content.length > 0)
}
