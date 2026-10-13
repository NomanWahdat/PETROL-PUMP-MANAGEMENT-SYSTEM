import { useI18n } from '../i18n';
import type { Language } from '../types/api';

export function LanguageSelect() {
  const { language, setLanguage, t } = useI18n();
  return <label className="language-select">
    <span>{t('language')}</span>
    <select value={language} onChange={event => {
      try { localStorage.setItem('station-language-explicit', 'true'); } catch { /* Preference storage is optional. */ }
      setLanguage(event.target.value as Language);
    }}>
      <option value="fa">{t('languageFa')}</option>
      <option value="ps">{t('languagePs')}</option>
      <option value="en">{t('languageEn')}</option>
    </select>
  </label>;
}
