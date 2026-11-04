// Same effect as Tauri's freezePrototype option.
if (!location.search.includes("nofreeze")) Object.freeze(Object.prototype);
window.__cspViolations = [];
document.addEventListener('securitypolicyviolation', (e) => window.__cspViolations.push(`${e.violatedDirective} ${e.blockedURI}`));
window.addEventListener('error', (e) => { (window.__errors = window.__errors || []).push(String(e.message)); });
window.addEventListener('unhandledrejection', (e) => { (window.__errors = window.__errors || []).push(String(e.reason && e.reason.stack || e.reason)); });
