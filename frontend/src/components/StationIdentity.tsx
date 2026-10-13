import { useState } from 'react';

export function FuelMark({ className = '' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="M11 41V10a3 3 0 0 1 3-3h16a3 3 0 0 1 3 3v31M8 41h28M16 13h12v12H16zM33 17l5 5v12a3 3 0 0 0 6 0V20l-6-7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M20 35h4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/></svg>;
}

export function StationIdentity({ src, name, className = '' }: { src?: string; name: string; className?: string }) {
  const [failed, setFailed] = useState('');
  return src && failed !== src ? <img className={'identity-logo '+className} src={src} alt={name} onError={() => setFailed(src)} /> : <span className={'identity-fallback '+className}><FuelMark /></span>;
}

export function StationIllustration() {
  return <svg className="station-illustration" viewBox="0 0 520 290" fill="none" aria-hidden="true">
    <path d="M24 258h472" stroke="#bfd6d1" strokeWidth="2"/>
    <rect x="72" y="92" width="360" height="29" rx="5" fill="#d6e9e3"/>
    <path d="M72 106h360" stroke="#477e70" strokeWidth="4"/>
    <path d="M94 121v137M410 121v137" stroke="#accac0" strokeWidth="10"/>
    <rect x="126" y="158" width="60" height="100" rx="7" fill="white" stroke="#5a8a7c" strokeWidth="2"/>
    <rect x="138" y="170" width="36" height="26" rx="3" fill="#eaf4f0" stroke="#8ab5a5"/>
    <path d="M154 207v24m-7-12h14M186 179l15 13v43a7 7 0 0 0 14 0v-49l-9-12" stroke="#5a8a7c" strokeWidth="3" strokeLinecap="round"/>
    <rect x="287" y="158" width="60" height="100" rx="7" fill="white" stroke="#5a8a7c" strokeWidth="2"/>
    <rect x="299" y="170" width="36" height="26" rx="3" fill="#eaf4f0" stroke="#8ab5a5"/>
    <path d="M315 207v24m-7-12h14M347 179l15 13v43a7 7 0 0 0 14 0v-49l-9-12" stroke="#5a8a7c" strokeWidth="3" strokeLinecap="round"/>
    <path d="M252 43c-9 14-17 22-17 32a17 17 0 0 0 34 0c0-10-8-18-17-32Z" fill="#6a9e8b"/>
    <path d="M242 76a10 10 0 0 0 10 10" stroke="white" strokeWidth="2" strokeLinecap="round"/>
    <rect x="440" y="166" width="37" height="70" rx="5" fill="#edf2f7" stroke="#a7bccb" strokeWidth="2"/>
    <path d="M458 236v22M448 180h21m-21 12h21m-21 12h21" stroke="#a7bccb" strokeWidth="2"/>
  </svg>;
}
