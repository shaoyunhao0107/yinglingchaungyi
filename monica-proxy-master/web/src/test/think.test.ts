import { describe, expect, it } from 'vitest'
import { splitThink } from '@/lib/think'

describe('splitThink', () => {
  it('returns a single text segment when there is no think tag', () => {
    expect(splitThink('hello world')).toEqual([{ type: 'text', content: 'hello world' }])
  })

  it('splits a closed think block from surrounding text', () => {
    expect(splitThink('before<think>reasoning</think>after')).toEqual([
      { type: 'text', content: 'before' },
      { type: 'think', content: 'reasoning' },
      { type: 'text', content: 'after' },
    ])
  })

  it('treats an unclosed think tag as still-streaming thinking', () => {
    expect(splitThink('intro<think>partial reasoning')).toEqual([
      { type: 'text', content: 'intro' },
      { type: 'think', content: 'partial reasoning' },
    ])
  })

  it('handles a think block at the very start', () => {
    expect(splitThink('<think>r</think>answer')).toEqual([
      { type: 'think', content: 'r' },
      { type: 'text', content: 'answer' },
    ])
  })

  it('drops empty segments', () => {
    expect(splitThink('<think></think>')).toEqual([])
  })

  it('supports multiple think blocks', () => {
    expect(splitThink('a<think>1</think>b<think>2</think>c')).toEqual([
      { type: 'text', content: 'a' },
      { type: 'think', content: '1' },
      { type: 'text', content: 'b' },
      { type: 'think', content: '2' },
      { type: 'text', content: 'c' },
    ])
  })
})
