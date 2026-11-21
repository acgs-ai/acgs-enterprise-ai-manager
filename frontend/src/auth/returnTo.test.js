import { describe, it, expect } from 'vitest'
import { sanitizeReturnTo } from './returnTo'

describe('sanitizeReturnTo', () => {
  it('keeps same-origin relative paths with query and hash', () => {
    expect(sanitizeReturnTo('/tasks?x=1#top')).toBe('/tasks?x=1#top')
  })

  it.each([
    'https://evil.example/',
    '//evil.example',
    '/\\evil.example',
    '\\\\evil.example',
    'javascript:alert(1)',
    'tasks',
    '/ok\n//evil.example',
    '/..//evil.example',
    '/%2e%2e//evil.example',
    '/a/..//evil',
    '/\\evil',
    '/%5c%5cevil',
    '/%2F%2Fevil',
    '/login',
    '/callback?code=1',
    '',
    null,
    undefined,
    ['/tasks'],
    42
  ])('rejects %j', (value) => {
    expect(sanitizeReturnTo(value)).toBe('/')
  })

  it('uses the provided fallback', () => {
    expect(sanitizeReturnTo('//x', '/home')).toBe('/home')
  })
})
