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
  card.innerHTML=`<p class="auth-eyebrow">AVIATION INTELLIGENCE NEXUS</p><h2 id="authHeading">Sign in to your research workspace</h2><p class="auth-intro">Access historical flight data, model calculations and saved research with your local account.</p>
    <p class="auth-status" role="status" aria-live="polite">Checking your session…</p>
    <form class="auth-form"><label>Username<input name="username" autocomplete="username" required maxlength="32"></label>
    <label>Password<input name="password" type="password" autocomplete="current-password" required maxlength="128"></label>
    <button class="btn" type="submit">Sign in</button></form>
    <button class="btn sm" type="button" data-auth-refresh>Check account setup</button>
    <button class="btn sm" type="button" data-auth-logout hidden>Sign out</button>
    <p class="auth-enrollment" hidden>First account setup is required. In the project terminal, run <code>python -m services.api.manage_users create --username shah --role admin</code>, choose your password privately, then select Check account setup.</p>`;
  parent.prepend(card);
  document.getElementById('authBoot')?.remove();
  const form=card.querySelector('form'),status=card.querySelector('.auth-status'),enrollment=card.querySelector('.auth-enrollment');
  const logout=card.querySelector('[data-auth-logout]');
  changed = value => {
    session=value;
    const user=value?.user;
    document.body.classList.toggle('research-locked',!user);
    document.title=user ? 'AIN | Research dashboard' : 'AIN | Sign in';
    card.querySelector('#authHeading').textContent=user ? 'Research account' : 'Sign in to your research workspace';
    card.querySelector('.auth-intro').textContent=user ? 'Your account permissions control connected research services.' : 'Access historical flight data, model calculations and saved research with your local account.';
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
