// Shared OIDC Authorization Code + PKCE client. Every page points this at
// the SAME realm/client (window.APP_CONFIG.realm/.clientId — generated
// into config.js at container start from KEYCLOAK_REALM/KC_CLIENT_ID, see
// ADR-0016, never hardcoded here) and the same sessionStorage key —
// there's one realm for everyone, admin vs operator is a role check on
// the token, not a separate login. Everything goes through the reverse
// proxy's /auth path (same origin as the page), so no CORS handling is
// needed here.

function b64url(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function randomString(len) {
  const arr = new Uint8Array(len);
  crypto.getRandomValues(arr);
  return b64url(arr.buffer).slice(0, len);
}

// crypto.subtle only exists in "secure contexts" (HTTPS, or localhost) —
// on a plain-HTTP LAN deployment like this one it's undefined, which used
// to make PKCE's code_challenge silently fail to ever get computed (the
// failure happened inside an un-awaited call, so it surfaced as nothing
// happening at all rather than a visible error). This pure-JS SHA-256
// keeps S256 PKCE working over plain HTTP; the native implementation is
// still preferred whenever it's actually available.
function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
function sha256Sync(bytes) {
  const K = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
  ];
  let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,
      h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;

  const len = bytes.length;
  const bitLen = len * 8;
  const padded = new Uint8Array(((len + 9 + 63) >> 6) << 6);
  padded.set(bytes);
  padded[len] = 0x80;
  const dv = new DataView(padded.buffer);
  dv.setUint32(padded.length - 4, bitLen >>> 0, false);
  dv.setUint32(padded.length - 8, Math.floor(bitLen / 0x100000000), false);

  const w = new Uint32Array(64);
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(offset + i * 4, false);
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >>> 3);
      const s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >>> 10);
      w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
    }
    let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,h=h7;
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
      const S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (S0 + maj) >>> 0;
      h=g; g=f; f=e; e=(d+temp1)>>>0; d=c; c=b; b=a; a=(temp1+temp2)>>>0;
    }
    h0=(h0+a)>>>0; h1=(h1+b)>>>0; h2=(h2+c)>>>0; h3=(h3+d)>>>0;
    h4=(h4+e)>>>0; h5=(h5+f)>>>0; h6=(h6+g)>>>0; h7=(h7+h)>>>0;
  }
  const out = new Uint8Array(32);
  const outDv = new DataView(out.buffer);
  [h0,h1,h2,h3,h4,h5,h6,h7].forEach((h, i) => outDv.setUint32(i * 4, h, false));
  return out.buffer;
}
async function sha256(text) {
  const data = new TextEncoder().encode(text);
  if (window.crypto && window.crypto.subtle) {
    try {
      return await crypto.subtle.digest("SHA-256", data);
    } catch (e) {
      // some browsers expose crypto.subtle but still throw on insecure
      // origins when the call is actually made — fall through to the JS one
    }
  }
  return sha256Sync(data);
}

function createAuthClient({ realm, clientId, storageKey }) {
  const base = "/auth";
  const authEndpoint = `${base}/realms/${realm}/protocol/openid-connect/auth`;
  const tokenEndpoint = `${base}/realms/${realm}/protocol/openid-connect/token`;
  const logoutEndpoint = `${base}/realms/${realm}/protocol/openid-connect/logout`;
  const redirectUri = window.location.origin + window.location.pathname;
  const verifierKey = `${storageKey}_pkce_verifier`;

  const client = {
    accessToken: null, refreshToken: null, expiresAt: 0, username: null, name: null, roles: [], _timer: null,

    load() {
      try {
        const raw = sessionStorage.getItem(storageKey);
        if (raw) Object.assign(this, JSON.parse(raw));
      } catch (e) {}
    },

    persist() {
      sessionStorage.setItem(storageKey, JSON.stringify({
        accessToken: this.accessToken, refreshToken: this.refreshToken,
        expiresAt: this.expiresAt, username: this.username, name: this.name, roles: this.roles,
      }));
    },

    // Re-derives username/name/roles straight from the accessToken's own
    // claims, rather than trusting whatever `load()` merged in from
    // sessionStorage. Needed because a session cached before a field was
    // added to this object (name/roles didn't always exist here) would
    // otherwise silently keep that field at its class default forever —
    // `init()`'s fast path returns early without ever calling
    // `storeTokens` again, so a stale-shaped cached blob previously stuck
    // around showing "?" for the avatar and the wrong role pill even
    // though the still-valid token it sat next to had the real claims.
    applyClaims() {
      if (!this.accessToken) return;
      try {
        const claims = JSON.parse(atob(this.accessToken.split(".")[1]));
        this.username = claims.preferred_username;
        this.name = claims.name || claims.preferred_username;
        this.roles = (claims.realm_access && claims.realm_access.roles) || [];
      } catch (e) {}
    },

    async init() {
      this.load();
      const params = new URLSearchParams(window.location.search);
      if (params.has("code")) {
        await this.exchangeCode(params.get("code"));
        window.history.replaceState({}, "", window.location.pathname);
        return !!this.accessToken;
      }
      if (this.accessToken && Date.now() < this.expiresAt - 15000) {
        this.applyClaims();
        this.scheduleRefresh((this.expiresAt - Date.now()) / 1000);
        return true;
      }
      if (this.refreshToken && await this.refresh()) return true;
      await this.redirectToLogin();
      return false;
    },

    async redirectToLogin() {
      const verifier = randomString(64);
      sessionStorage.setItem(verifierKey, verifier);
      const challenge = b64url(await sha256(verifier));
      const url = new URL(authEndpoint, window.location.origin);
      url.searchParams.set("client_id", clientId);
      url.searchParams.set("redirect_uri", redirectUri);
      url.searchParams.set("response_type", "code");
      url.searchParams.set("scope", "openid profile email");
      url.searchParams.set("code_challenge", challenge);
      url.searchParams.set("code_challenge_method", "S256");
      window.location.href = url.toString();
    },

    async exchangeCode(code) {
      const verifier = sessionStorage.getItem(verifierKey) || "";
      const body = new URLSearchParams({
        grant_type: "authorization_code", client_id: clientId, code,
        redirect_uri: redirectUri, code_verifier: verifier,
      });
      const res = await fetch(tokenEndpoint, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
      if (!res.ok) return this.redirectToLogin();
      this.storeTokens(await res.json());
    },

    async refresh() {
      try {
        const body = new URLSearchParams({ grant_type: "refresh_token", client_id: clientId, refresh_token: this.refreshToken });
        const res = await fetch(tokenEndpoint, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
        if (!res.ok) return false;
        this.storeTokens(await res.json());
        return true;
      } catch (e) { return false; }
    },

    storeTokens(data) {
      this.accessToken = data.access_token;
      this.refreshToken = data.refresh_token;
      this.expiresAt = Date.now() + data.expires_in * 1000;
      this.applyClaims();
      this.persist();
      this.scheduleRefresh(data.expires_in);
    },

    hasRole(role) { return this.roles.includes(role); },
    hasAnyRole(roles) { return roles.some((r) => this.roles.includes(r)); },

    scheduleRefresh(expiresIn) {
      if (this._timer) clearTimeout(this._timer);
      this._timer = setTimeout(() => this.refresh(), Math.max((expiresIn - 30) * 1000, 5000));
    },

    authHeader() { return { Authorization: `Bearer ${this.accessToken}` }; },

    async apiFetch(path, opts = {}) {
      opts.headers = Object.assign({}, opts.headers, this.authHeader());
      let res = await fetch(path, opts);
      if (res.status === 401) {
        if (await this.refresh()) {
          opts.headers = Object.assign({}, opts.headers, this.authHeader());
          res = await fetch(path, opts);
        } else {
          this.redirectToLogin();
          throw new Error("unauthorized");
        }
      }
      return res;
    },

    logout() {
      sessionStorage.removeItem(storageKey);
      sessionStorage.removeItem(verifierKey);
      const url = new URL(logoutEndpoint, window.location.origin);
      url.searchParams.set("client_id", clientId);
      url.searchParams.set("post_logout_redirect_uri", redirectUri);
      window.location.href = url.toString();
    },
  };

  return client;
}
