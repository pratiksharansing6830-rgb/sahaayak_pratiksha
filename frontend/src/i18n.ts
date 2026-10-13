// Add Marathi etc. by filling dict.mr with translations reviewed by a native speaker.
const dict: Record<string, Record<string, string>> = { en: {}, mr: {} };
let lang = "en";
export const setLanguage = (l: string) => { lang = l; };
export const t = (s: string) => dict[lang]?.[s] ?? s;