const $ = (id) => document.getElementById(id);
const say = (t, ok) => {
  $("msg").textContent = t;
  $("msg").style.color = ok ? "#7fb89a" : "#d9826f";
};

chrome.storage.local.get(["endpoint", "token"]).then(({ endpoint, token }) => {
  $("endpoint").value = endpoint || "";
  $("token").value = token || "";
});

function readFields() {
  const endpoint = $("endpoint").value.trim().replace(/\/+$/, "");
  const token = $("token").value.replace(/\s+/g, "");
  if (/[•·*]/.test(token)) throw new Error("That's the masked token (dots). Use the copy button next to the token on the Captures page.");
  let origin;
  try {
    origin = new URL(endpoint).origin;
  } catch {
    throw new Error("That address doesn't look like a URL.");
  }
  return { endpoint, token, origin };
}

$("save").onclick = async () => {
  let f;
  try {
    f = readFields();
  } catch (e) {
    return say(e.message);
  }
  // Ask Chrome for access to exactly this one address.
  const granted = await chrome.permissions.request({ origins: [f.origin + "/*"] });
  if (!granted) return say("Chrome permission was declined — the extension can't reach your Rep Index without it.");
  await chrome.storage.local.set({ endpoint: f.endpoint, token: f.token });
  say(`Saved (token ${f.token.length} characters).`, true);
};

// Tests exactly what is in the fields, saved or not.
$("test").onclick = async () => {
  let f;
  try {
    f = readFields();
  } catch (e) {
    return say(e.message);
  }
  try {
    // An empty capture: 400 means the token was accepted; 401 means it wasn't.
    const r = await fetch(f.endpoint + "/api/capture", {
      method: "POST",
      headers: { "content-type": "application/json", "x-capture-token": f.token },
      body: JSON.stringify({ url: "", html: "" }),
    });
    if (r.status === 400) say("Connected — token accepted. Click Save if you haven't yet.", true);
    else if (r.status === 401) say(`Reached the Rep Index, but the token (${f.token.length} characters) was rejected. It should be 32 characters.`);
    else say(`Unexpected answer: ${r.status}`);
  } catch (e) {
    say(`Couldn't reach ${f.endpoint} — are you on your home network or WireGuard? (${e.message})`);
  }
};
