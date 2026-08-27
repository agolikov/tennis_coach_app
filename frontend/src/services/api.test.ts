import { buildUrl } from './api';

describe('buildUrl', () => {
  it('resolves a relative API base against the current origin', () => {
    expect(buildUrl('/videos/upload', undefined, '/v0')).toBe(
      `${window.location.origin}/v0/videos/upload`
    );
  });

  it('preserves an absolute API base', () => {
    expect(
      buildUrl('/videos/upload', undefined, 'https://api.example.com/v0')
    ).toBe('https://api.example.com/v0/videos/upload');
  });
});
