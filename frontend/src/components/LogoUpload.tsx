import { useState } from 'react';
import { useI18n } from '../i18n';
import { api, errorKey } from '../services/api';
import { StationIdentity } from './StationIdentity';

export function LogoUpload({ endpoint, name, src, onUploaded }: { endpoint: string; name: string; src?: string; onUploaded?: () => Promise<void> }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState('');
  const [saved, setSaved] = useState(false);
  return <section className="branding-editor"><h2>{t('logo')}</h2><p className="muted">{t('logoHelp')} {t('publicLogoHelp')}</p>
    <StationIdentity className="logo-preview" src={preview || src} name={name} />
    <form onSubmit={event => {
      event.preventDefault(); if (!file || busy) return;
      setBusy(true); setError(null); setSaved(false);
      const body = new FormData(); body.append('logo', file);
      void api<{ logo_url: string }>(endpoint, { method: 'POST', body }).then(async result => { setPreview(result.logo_url); await onUploaded?.(); setSaved(true); }).catch(setError).finally(() => setBusy(false));
    }}><label className="file-field"><span>{t('logo')}</span><input type="file" accept="image/png,image/jpeg,image/webp" required disabled={busy} onChange={event => { setFile(event.target.files?.[0] || null); setSaved(false); }} /></label>
      {error != null && <p className="error-message" role="alert">{t(errorKey(error))}</p>}
      {saved && <p className="success-message" role="status">{t('brandingSaved')}</p>}
      <button disabled={!file || busy} aria-busy={busy}>{t(busy ? 'saving' : 'uploadLogo')}</button>
    </form>
  </section>;
}
