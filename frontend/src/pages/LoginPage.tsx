import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { LanguageSelect } from '../components/LanguageSelect';
import { useAuth } from '../features/auth/AuthContext';
import { useConnection } from '../hooks/useConnection';
import { useI18n } from '../i18n';
import { api, errorKey, type ApiError } from '../services/api';
import { StationIdentity, StationIllustration, FuelMark } from '../components/StationIdentity';

interface Branding { name: string; slug: string; primary_color: string; logo_url: string }
function rememberedStation() { try { return localStorage.getItem('login-station') || ''; } catch { return ''; } }

export function LoginPage() {
  const { user, signIn } = useAuth();
  const { t } = useI18n();
  const online = useConnection();
  const [params, setParams] = useSearchParams();
  const slug = params.has('station') ? params.get('station') || '' : rememberedStation();
  const [stationCode, setStationCode] = useState(slug);
  const [branding, setBranding] = useState<Branding | null>(null);
  const [brandingError, setBrandingError] = useState(false);
  const [brandingLoading, setBrandingLoading] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let current = true;
    setBranding(null); setBrandingError(false); setBrandingLoading(Boolean(slug)); setStationCode(slug);
    if (slug) void api<Branding>('/branding/'+encodeURIComponent(slug)+'/').then(value => { if (current) setBranding(value); }).catch(() => { if (current) setBrandingError(true); }).finally(() => { if (current) setBrandingLoading(false); });
    return () => { current = false; };
  }, [slug]);
  if (user) return <Navigate to="/" replace />;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !online) return;
    setBusy(true); setError(null);
    try { await signIn(username.trim(), password); }
    catch (error) { setError(error as ApiError); }
    finally { setBusy(false); }
  }
  return <div className="login-page">
    <header className="login-topbar"><span className="login-app-name"><FuelMark />{t('appName')}</span><div className="login-tools"><ConnectionStatus /><LanguageSelect /></div></header>
    <main className="login-layout">
      <section className="login-story" aria-labelledby="login-station-title">
        <StationIdentity src={branding?.logo_url} name={branding?.name || t('appName')} className="login-logo" />
        <p className="eyebrow">{t('stationWorkspace')}</p>
        <h1 id="login-station-title">{branding?.name || t('loginHeadline')}</h1>
        <p className="login-story-intro">{t('loginStory')}</p>
        <StationIllustration />
        <ul className="login-highlights"><li>{t('loginFuel')}</li><li>{t('loginStock')}</li><li>{t('loginCash')}</li></ul>
      </section>
      <section className="login-panel" aria-labelledby="sign-in-title">
      <p className="eyebrow">{branding?.name || t('stationWorkspace')}</p>
      <h2 id="sign-in-title">{t('signIn')}</h2>
      <p className="muted">{t('loginIntro')}</p>
      <form onSubmit={event => void submit(event)}>
        <label htmlFor="username">{t('username')}</label>
        <input id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
          dir="auto" maxLength={150} required value={username} onChange={event => setUsername(event.target.value)} />
        <label htmlFor="password">{t('password')}</label>
        <input id="password" name="password" type="password" autoComplete="current-password" maxLength={256}
          required value={password} onChange={event => setPassword(event.target.value)} />
        {error && <p className="error-message" role="alert">{t(errorKey(error))}</p>}
        {!online && <p className="notice" role="status">{t('offlineHelp')}</p>}
        <button type="submit" disabled={busy || !online} aria-busy={busy}>{t(busy ? 'signingIn' : 'signIn')}</button>
      </form>
      <details className="login-station-choice"><summary>{t('chooseLoginStation')}</summary>
        <form onSubmit={event => { event.preventDefault(); setParams({ station: stationCode.trim() }); }}>
          <label htmlFor="station-code">{t('stationCode')}</label><input id="station-code" value={stationCode} onChange={event => setStationCode(event.target.value)} maxLength={50} autoCapitalize="none" dir="ltr" />
          <button className="secondary" disabled={brandingLoading}>{t('useStation')}</button>
          {brandingLoading && <p role="status">{t('loading')}</p>}
          {brandingError && <p className="error-text" role="alert">{t('loginStationMissing')}</p>}
        </form>
      </details>
      <p className="login-footer">{t('loginAccessHelp')}</p>
      </section>
    </main>
    <footer className="login-page-footer">{t('loginFooter')}</footer>
  </div>;
}
