import { describe, it, expect } from 'vitest';
import { getSafeExternalUrl, SAFE_EXTERNAL_LINK_PROPS } from '../../frontend/src/utils/urlSecurity';

describe('urlSecurity utilities', () => {
  it('should validate secure HTTP and HTTPS URLs', () => {
    expect(getSafeExternalUrl('https://example.com/job')).toBe('https://example.com/job');
    expect(getSafeExternalUrl('http://localhost:8000/health')).toBe('http://localhost:8000/health');
  });

  it('should reject dangerous javascript and data URIs returning null', () => {
    expect(getSafeExternalUrl('javascript:alert(1)')).toBeNull();
    expect(getSafeExternalUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
    expect(getSafeExternalUrl('vbscript:msgbox(1)')).toBeNull();
  });

  it('should reject empty or invalid values returning null', () => {
    expect(getSafeExternalUrl('')).toBeNull();
    expect(getSafeExternalUrl('   ')).toBeNull();
    expect(getSafeExternalUrl(null)).toBeNull();
    expect(getSafeExternalUrl(undefined)).toBeNull();
  });

  it('should provide safe rel and target attributes to prevent tabnabbing', () => {
    expect(SAFE_EXTERNAL_LINK_PROPS.target).toBe('_blank');
    expect(SAFE_EXTERNAL_LINK_PROPS.rel).toBe('noopener noreferrer');
  });
});
