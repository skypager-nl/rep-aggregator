const $ = (id) => document.getElementById(id);
$("opts").onclick = (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
};

(async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const { endpoint, token } = await chrome.storage.local.get(["endpoint", "token"]);
  if (!endpoint || !token) {
    $("status").innerHTML = 'Not set up yet — add your Rep Index address and token in <a href="#" id="o2">Settings</a>.';
    $("o2").onclick = () => chrome.runtime.openOptionsPage();
    return;
  }
  if (!tab?.url || !/^https:\/\/forum\.replica-watch\.info\/threads\//.test(tab.url)) {
    $("status").textContent = "Open an RWI thread to capture it.";
    return;
  }
  $("status").textContent = (tab.title || "").replace(/ \| Replica Watch Info$/, "");
  for (const mode of ["thread", "page"]) {
    $(mode).disabled = false;
    $(mode).onclick = async () => {
      const r = await chrome.runtime.sendMessage({ type: "start", tabId: tab.id, mode });
      if (!r?.ok) $("status").textContent = r?.error || "Couldn't start.";
      else window.close();
    };
  }
})();
