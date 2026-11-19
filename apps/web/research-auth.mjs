let session = null;
let changed = null;

export function canCalculate() { return ['admin','researcher'].includes(session?.user?.role); }
export async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET' && session?.csrf_token) headers.set('X-CSRF-Token',session.csrf_token);
  const response = await fetch(url,{...options,headers,credentials:'same-origin',cache:'no-store'});
  if (response.status===401 && session?.user) {session=null;changed?.(null);}
  return response;
}

export function mountAuth(parent,onChange) {
  const card=document.createElement('section');
  card.className='research-card research-auth';
  card.setAttribute('aria-labelledby','authHeading');
  card.innerHTML=`<div class="auth-visual">
      <img class="auth-hero-image" src="assets/login-family-aviation.png" alt="AI-generated scene of an Emirati family travelling through a Dubai airport beside a passenger aircraft.">
      <div class="auth-visual-shade"></div>
      <div class="auth-uae-flag">
        <svg viewBox="0 0 240 120" role="img" aria-label="Flag of the United Arab Emirates" xmlns="http://www.w3.org/2000/svg">
          <defs><linearGradient id="uaeFlagSilk" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity=".16"/><stop offset=".28" stop-color="#000" stop-opacity=".08"/><stop offset=".55" stop-color="#fff" stop-opacity=".18"/><stop offset=".8" stop-color="#000" stop-opacity=".1"/><stop offset="1" stop-color="#fff" stop-opacity=".05"/></linearGradient></defs>
          <path fill="#009a49" d="M0 0h240v40H0z"/><path fill="#fff" d="M0 40h240v40H0z"/><path fill="#111" d="M0 80h240v40H0z"/>
          <path fill="#ed1c24" d="M0 0h60v120H0z"/><path fill="url(#uaeFlagSilk)" d="M0 0h240v120H0z"/>
        </svg>
        <span lang="ar" dir="rtl">الإمارات العربية المتحدة</span>
      </div>
      <div class="auth-visual-brand"><span class="auth-brand-mark" aria-hidden="true">✈</span><div><strong>AIN<span>.</span></strong><small>AVIATION INTELLIGENCE NEXUS</small></div></div>
      <div class="auth-hero-copy"><p class="auth-hero-eyebrow">EMIRATES-INSPIRED · DUBAI SPIRIT</p><p class="auth-arabic" lang="ar" dir="rtl">أهلاً بكم</p><h1>A world of journeys.<br>A clearer perspective.</h1><p>Connecting the people, possibilities and intelligence behind every journey.</p><div class="auth-hero-rule"></div><span>People at the heart. Intelligence at the horizon.</span></div>
      <div class="auth-visual-footer"><span>DUBAI, UNITED ARAB EMIRATES</span><span>AI-generated travel concept</span></div>
    </div><div class="auth-panel"><div class="auth-panel-inner">
    <div class="auth-panel-top"><span class="auth-panel-monogram">AIN<span>.</span></span><span lang="ar" dir="rtl">مرحباً بعودتك</span></div>
    <p class="auth-eyebrow">YOUR AVIATION RESEARCH WORKSPACE</p><h2 id="authHeading">Welcome back</h2><p class="auth-intro">Sign in to explore your aviation intelligence workspace.</p>
    <p class="auth-status" role="status" aria-live="polite">Checking your session…</p>
    <form class="auth-form"><label>Username<input name="username" autocomplete="username" required maxlength="32" placeholder="Enter your username"></label>
    <label>Password<input name="password" type="password" autocomplete="current-password" required maxlength="128" placeholder="Enter your password"></label>
    <button class="btn" type="submit">Sign in</button></form>
    <button class="btn sm" type="button" data-auth-refresh>Check account setup</button>
    <button class="btn sm" type="button" data-auth-logout hidden>Sign out</button>
    <p class="auth-enrollment" hidden>First account setup is required. In the project terminal, run <code>python -m services.api.manage_users create --username shah --role admin</code>, choose your password privately, then select Check account setup.</p>
    <div class="auth-panel-footer"><span class="auth-footer-line"></span><p>Independent aviation portfolio.<br>Not affiliated with or endorsed by Emirates.</p><span>Thoughtfully built for the future of aviation.</span></div>
    </div></div>`;
  parent.prepend(card);
  document.getElementById('authBoot')?.remove();
  const form=card.querySelector('form'),status=card.querySelector('.auth-status'),enrollment=card.querySelector('.auth-enrollment');
  const logout=card.querySelector('[data-auth-logout]');
  changed = value => {
    session=value;
    const user=value?.user;
    document.body.classList.toggle('research-locked',!user);
    document.title=user ? 'AIN | Research dashboard' : 'AIN | Sign in';
    card.querySelector('#authHeading').textContent=user ? 'Research account' : 'Welcome back';
    card.querySelector('.auth-intro').textContent=user ? 'Your account permissions control connected research services.' : 'Sign in to explore your aviation intelligence workspace.';
    form.hidden=!!user; logout.hidden=!user;
    status.textContent=user ? `Signed in as ${user.username} · ${user.role}. Sessions expire after eight hours.` : 'Sign in to access connected research services.';
    onChange(user || null);
  };
  async function check() {
    try {
      const response=await apiFetch('/api/v1/auth/session');
      if(!response.ok)throw new Error('Unavailable');
      const value=await response.json(); changed(value.authenticated ? value : null);
      enrollment.hidden=!value.enrollment_required;
    } catch {changed(null);status.textContent='The account service is unavailable. Start the local backend and check again.';}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault(); const button=form.querySelector('button'); button.disabled=true;
    try {
      const response=await apiFetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});
      const value=await response.json(); form.elements.password.value='';
      if(!response.ok){status.textContent=response.status===429?'Too many failed attempts. Try again after one minute.':'Sign-in failed. Check your username and password.';return;}
      enrollment.hidden=true;changed(value);
    } catch {status.textContent='Sign-in could not reach the account service.';}
    finally {button.disabled=false;}
  });
  logout.addEventListener('click',async()=>{
    try {const response=await apiFetch('/api/v1/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      if(!response.ok)throw new Error('Unavailable');changed(null);
    } catch {status.textContent='Sign-out could not be confirmed. Check the backend and try again.';}
  });
  card.querySelector('[data-auth-refresh]').addEventListener('click',check);
  check();
}
