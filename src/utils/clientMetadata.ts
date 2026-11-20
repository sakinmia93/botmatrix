/**
 * Client Device Metadata & Security Fingerprinting Utility
 * Collects high-fidelity hardware, environment, network, and canvas fingerprinting data
 * for real backend authentication and session integrity verification.
 */

export interface ClientMetadata {
  screen_width: number;
  screen_height: number;
  viewport_width: number;
  viewport_height: number;
  color_depth: number;
  pixel_ratio: number;
  timezone: string;
  timezone_offset: number;
  browser_language: string;
  languages: string[];
  platform: string;
  vendor: string;
  hardware_concurrency: number;
  device_memory: number;
  max_touch_points: number;
  is_touch_device: boolean;
  is_mobile: boolean;
  cookies_enabled: boolean;
  do_not_track: string | null;
  online: boolean;
  pdf_viewer_enabled: boolean;
  connection_type: string | null;
  connection_effective_type: string;
  connection_downlink: number;
  connection_rtt: number;
  connection_save_data: boolean;
  page_path: string;
  referrer: string;
  referrer_history: string[];
  session_storage_available: boolean;
  local_storage_available: boolean;
  indexed_db_available: boolean;
  page_load_time: number;
  dom_content_loaded_time: number;
  battery_level: number;
  battery_charging: boolean;
  canvas_fingerprint: string;
  webgl_vendor: string;
  webgl_renderer: string;
  client_version: string;
  client_build: string;
  push_permission: string;
}

export function getCanvasFingerprint(): string {
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 50;
    const ctx = canvas.getContext('2d');
    if (!ctx) return 'AA//8L/X/iAAAABklEQVQDAJY4llqolPRIAAAAAElFTkSuQmCC';
    ctx.textBaseline = 'top';
    ctx.font = "14px 'Arial'";
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = '#f60';
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = '#069';
    ctx.fillText('TeleBot, Matrix 2026', 2, 15);
    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
    ctx.fillText('TeleBot, Matrix 2026', 4, 17);
    const dataUrl = canvas.toDataURL();
    return dataUrl.slice(-44);
  } catch {
    return 'AA//8L/X/iAAAABklEQVQDAJY4llqolPRIAAAAAElFTkSuQmCC';
  }
}

export function getWebGLInfo(): { vendor: string; renderer: string } {
  try {
    const canvas = document.createElement('canvas');
    const gl = (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')) as WebGLRenderingContext | null;
    if (!gl) {
      return {
        vendor: 'Google Inc. (AMD)',
        renderer: 'ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
      };
    }
    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    if (!debugInfo) {
      return {
        vendor: gl.getParameter(gl.VENDOR) || 'Google Inc. (AMD)',
        renderer: gl.getParameter(gl.RENDERER) || 'ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
      };
    }
    return {
      vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || 'Google Inc. (AMD)',
      renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || 'ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
    };
  } catch {
    return {
      vendor: 'Google Inc. (AMD)',
      renderer: 'ANGLE (AMD, AMD Radeon(TM) Graphics (0x000015C8) Direct3D11 vs_5_0 ps_5_0, D3D11)',
    };
  }
}

export async function collectClientMetadata(): Promise<ClientMetadata> {
  const isBrowser = typeof window !== 'undefined';
  const nav = isBrowser ? window.navigator : ({} as any);
  const conn = nav?.connection || (nav as any)?.mozConnection || (nav as any)?.webkitConnection;

  const webgl = getWebGLInfo();
  const canvasFp = getCanvasFingerprint();

  let batteryLevel = 0.4;
  let batteryCharging = false;
  try {
    if ((nav as any)?.getBattery) {
      const b = await (nav as any).getBattery();
      batteryLevel = b.level || 0.4;
      batteryCharging = b.charging || false;
    }
  } catch {
    // default
  }

  const perf = isBrowser && window.performance ? window.performance.timing : null;
  const pageLoadTime = perf && perf.loadEventEnd > 0 ? perf.loadEventEnd - perf.navigationStart : 2671;
  const domTime = perf && perf.domContentLoadedEventEnd > 0 ? perf.domContentLoadedEventEnd - perf.navigationStart : 2097;

  let pushPerm = 'granted';
  try {
    if (typeof Notification !== 'undefined') {
      pushPerm = Notification.permission;
    }
  } catch {
    // default
  }

  return {
    screen_width: isBrowser ? window.screen.width : 1280,
    screen_height: isBrowser ? window.screen.height : 800,
    viewport_width: isBrowser ? window.innerWidth : 252,
    viewport_height: isBrowser ? window.innerHeight : 665,
    color_depth: isBrowser ? window.screen.colorDepth || 24 : 24,
    pixel_ratio: isBrowser ? window.devicePixelRatio || 1.5 : 1.5,
    timezone: isBrowser ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Dhaka' : 'Asia/Dhaka',
    timezone_offset: isBrowser ? new Date().getTimezoneOffset() : -360,
    browser_language: isBrowser ? nav.language || 'en-US' : 'en-US',
    languages: isBrowser && nav.languages ? Array.from(nav.languages) : ['en-US', 'bn-BD', 'bn-IN', 'bn', 'en'],
    platform: isBrowser ? nav.platform || 'Win32' : 'Win32',
    vendor: isBrowser ? nav.vendor || 'Google Inc.' : 'Google Inc.',
    hardware_concurrency: isBrowser ? nav.hardwareConcurrency || 12 : 12,
    device_memory: isBrowser ? (nav as any).deviceMemory || 16 : 16,
    max_touch_points: isBrowser ? nav.maxTouchPoints || 0 : 0,
    is_touch_device: isBrowser ? (nav.maxTouchPoints > 0) : false,
    is_mobile: isBrowser ? /Mobi|Android/i.test(nav.userAgent) : false,
    cookies_enabled: isBrowser ? nav.cookieEnabled : true,
    do_not_track: isBrowser ? nav.doNotTrack || null : null,
    online: isBrowser ? nav.onLine : true,
    pdf_viewer_enabled: isBrowser ? (nav as any).pdfViewerEnabled ?? true : true,
    connection_type: conn?.type || null,
    connection_effective_type: conn?.effectiveType || '4g',
    connection_downlink: conn?.downlink || 10,
    connection_rtt: conn?.rtt || 50,
    connection_save_data: conn?.saveData || false,
    page_path: isBrowser ? window.location.pathname || '/login' : '/login',
    referrer: isBrowser ? document.referrer || 'https://botmatrix.com/bots/75552942' : 'https://botmatrix.com/bots/75552942',
    referrer_history: [isBrowser ? document.referrer || 'https://botmatrix.com/bots/75552942' : 'https://botmatrix.com/bots/75552942'],
    session_storage_available: typeof sessionStorage !== 'undefined',
    local_storage_available: typeof localStorage !== 'undefined',
    indexed_db_available: typeof indexedDB !== 'undefined',
    page_load_time: pageLoadTime > 0 ? pageLoadTime : 2671,
    dom_content_loaded_time: domTime > 0 ? domTime : 2097,
    battery_level: batteryLevel,
    battery_charging: batteryCharging,
    canvas_fingerprint: canvasFp,
    webgl_vendor: webgl.vendor,
    webgl_renderer: webgl.renderer,
    client_version: '2.0.0',
    client_build: '2026-09-27',
    push_permission: pushPerm,
  };
}
