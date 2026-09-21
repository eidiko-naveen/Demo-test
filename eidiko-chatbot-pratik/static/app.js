const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const main = document.getElementById("messages");
const connectBtn = document.getElementById("connect-btn");
const disconnectBtn = document.getElementById("disconnect-btn");

function addMessage(role, text, results, action) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;

  if (results && results.length) {
    const list = document.createElement("div");
    list.className = "results";
    results.forEach((r) => {
      const a = document.createElement("a");
      a.className = "result-link";
      a.href = r.link;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.innerHTML = `<div class="rtitle">${escapeHtml(r.title || "(untitled)")}</div>
                     <div class="rmeta">${escapeHtml(r.source)} · ${escapeHtml(r.meta || "")} · ${escapeHtml(r.date || "")}</div>`;
      list.appendChild(a);

      if (r.source === "calendar") {
        const details = document.createElement("div");
        details.className = "rmeta";
        const time = [r.start, r.end].filter(Boolean).join(" → ");
        const people = (r.attendees || []).join(", ");
        details.textContent =
          [time, r.location, people].filter(Boolean).join(" · ");
        list.appendChild(details);

        if (r.meet_link) {
          const meet = document.createElement("a");
          meet.className = "result-link attachment-link";
          meet.href = r.meet_link;
          meet.target = "_blank";
          meet.rel = "noopener noreferrer";
          meet.innerHTML = `<div class="rtitle">🎥 Google Meet</div>
                            <div class="rmeta">Join existing meeting</div>`;
          list.appendChild(meet);
        }
      }

      (r.attachments || []).forEach((att) => {
        const dl = document.createElement("a");
        dl.className = "result-link attachment-link";
        dl.href = att.download_url;
        dl.innerHTML = `<div class="rtitle">⬇ ${escapeHtml(att.filename)}</div>
                         <div class="rmeta">download attachment</div>`;
        list.appendChild(dl);
      });
    });
    div.appendChild(list);
  }

  if (action && action.id) {
    const box = document.createElement("div");
    box.className = "action-confirm";
    const label = document.createElement("div");
    label.className = "rtitle";
    label.textContent = action.confirm_text || "Confirm this action?";
    box.appendChild(label);

    if (action.type === "send_gmail" && action.body_preview) {
      const preview = document.createElement("div");
      preview.className = "rmeta";
      preview.textContent = `Body: ${action.body_preview}`;
      box.appendChild(preview);
    }

    if (action.type === "create_calendar_event") {
      const details = document.createElement("div");
      details.className = "rmeta";
      details.textContent = `Event: ${action.summary}`;
      box.appendChild(details);

      const when = document.createElement("div");
      when.className = "rmeta";
      when.textContent = `When: ${action.start} – ${action.end}`;
      box.appendChild(when);

      const attendees = document.createElement("div");
      attendees.className = "rmeta";
      attendees.textContent = `Attendees: ${(action.attendees || []).join(", ") || "None"}`;
      box.appendChild(attendees);

      const meet = document.createElement("div");
      meet.className = "rmeta";
      meet.textContent = "Google Meet: A Meet link will be generated";
      box.appendChild(meet);
    }

    if (action.type === "update_calendar_event") {
      const details = document.createElement("div"); details.className = "rmeta";
      details.textContent = `Event: ${action.summary}`; box.appendChild(details);
      const when = document.createElement("div"); when.className = "rmeta";
      when.textContent = `New time: ${action.new_start} – ${action.new_end}`; box.appendChild(when);
      const attendees = document.createElement("div"); attendees.className = "rmeta";
      attendees.textContent = `Attendees: ${(action.attendees || []).join(", ") || "None"}`; box.appendChild(attendees);
    }

    if (action.type === "cancel_calendar_events") {
      const details = document.createElement("div");
      details.className = "rmeta";
      details.textContent = `Events: ${(action.events || []).join(", ") || "None"}`;
      box.appendChild(details);
      const warning = document.createElement("div");
      warning.className = "rmeta";
      warning.textContent = `This will cancel ${action.count || (action.events || []).length} Calendar event(s) and notify attendees.`;
      box.appendChild(warning);
    }

    if (action.type === "cancel_calendar_event") {
      const details = document.createElement("div"); details.className = "rmeta";
      details.textContent = `Event: ${action.summary}`; box.appendChild(details);
      const warning = document.createElement("div"); warning.className = "rmeta";
      warning.textContent = "This will cancel the Calendar event and notify attendees."; box.appendChild(warning);
    }

    if (action.type === "multi_action") {
      const details = document.createElement("div"); details.className = "rmeta";
      details.textContent = `File: ${action.file || "(none)"}`; box.appendChild(details);
      const recipient = document.createElement("div"); recipient.className = "rmeta";
      recipient.textContent = `Recipient: ${action.recipient || "(none)"}`; box.appendChild(recipient);
      const meeting = document.createElement("div"); meeting.className = "rmeta";
      meeting.textContent = `Meeting: ${action.summary || "Meeting"}`; box.appendChild(meeting);
      const when = document.createElement("div"); when.className = "rmeta";
      when.textContent = `When: ${action.start || ""} – ${action.end || ""}`; box.appendChild(when);
      const attendees = document.createElement("div"); attendees.className = "rmeta";
      attendees.textContent = `Attendees: ${(action.attendees || []).join(", ") || "None"}`; box.appendChild(attendees);
      const meet = document.createElement("div"); meet.className = "rmeta";
      meet.textContent = "Google Meet: A Meet link will be generated"; box.appendChild(meet);
    }

    if (action.type === "send_drive_file_gmail") {
      const file = document.createElement("div");
      file.className = "rmeta";
      file.textContent = `Document: ${action.source}`;
      box.appendChild(file);
      const recipient = document.createElement("div");
      recipient.className = "rmeta";
      recipient.textContent = `Recipient: ${action.recipient}`;
      box.appendChild(recipient);
      const subject = document.createElement("div");
      subject.className = "rmeta";
      subject.textContent = `Subject: ${action.subject}`;
      box.appendChild(subject);
      if (action.body_preview) {
        const body = document.createElement("div");
        body.className = "rmeta";
        body.textContent = `Body: ${action.body_preview}`;
        box.appendChild(body);
      }
    }

    const confirm = document.createElement("button");
    confirm.className = "confirm-btn";
    confirm.textContent = "Confirm";
    const cancel = document.createElement("button");
    cancel.className = "cancel-btn";
    cancel.textContent = "Cancel";

    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      cancel.disabled = true;
      confirm.textContent = "Working...";
      try {
        const res = await fetch("/api/action/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action_id: action.id }),
        });
        const data = await res.json();
        addMessage("bot", data.reply || "Action completed.", data.results || []);
      } catch (err) {
        addMessage("bot", "I couldn't complete the action. Please try again.");
      }
    });

    cancel.addEventListener("click", async () => {
      confirm.disabled = true;
      cancel.disabled = true;
      await fetch("/api/action/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: action.id }),
      });
      box.remove();
      addMessage("bot", "Okay, I didn't make any changes.");
    });

    box.appendChild(confirm);
    box.appendChild(cancel);
    div.appendChild(box);
  }

  main.appendChild(div);
  main.scrollTop = main.scrollHeight;
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();
  connectBtn.dataset.connected = data.authenticated;
  connectBtn.textContent = data.authenticated ? "Connected" : "Connect Google Account";
  connectBtn.disabled = !!data.authenticated;
  disconnectBtn.disabled = !data.authenticated;
}

disconnectBtn.addEventListener("click", async () => {
  if (disconnectBtn.disabled) return;
  disconnectBtn.disabled = true;
  disconnectBtn.textContent = "Disconnecting...";
  await fetch("/api/disconnect", { method: "POST" });
  disconnectBtn.textContent = "Disconnect";
  addMessage("bot", "Disconnected. Your Google access has been revoked and the local session cleared.");
  refreshStatus();
});

connectBtn.addEventListener("click", async () => {
  if (connectBtn.dataset.connected === "true") return;
  connectBtn.textContent = "Opening Google sign-in...";

  const res = await fetch("/api/authorize");
  const data = await res.json();

  if (!data.ok) {
    addMessage("bot", `Couldn't connect: ${data.error}`);
    connectBtn.textContent = "Connect Google Account";
    return;
  }

  const popup = window.open(data.authUrl, "_blank", "noopener,noreferrer");
  if (!popup) {
    addMessage("bot", "Your browser blocked the pop-up. Click below to sign in:", [
      { title: "Sign in with Google", meta: "opens in a new tab", date: "", link: data.authUrl, source: "google" },
    ]);
  } else {
    addMessage("bot", "A Google sign-in tab just opened — approve the requested Gmail, Calendar, and Drive access there, then come back here.");
  }

  connectBtn.textContent = "Waiting for sign-in...";
  pollForConnection();
});

async function pollForConnection(attemptsLeft = 60) {
  if (attemptsLeft <= 0) {
    connectBtn.textContent = "Connect Google Account";
    return;
  }
  await new Promise((r) => setTimeout(r, 2000));
  const res = await fetch("/api/status");
  const data = await res.json();
  if (data.authenticated) {
    connectBtn.dataset.connected = "true";
    connectBtn.textContent = "Connected";
    connectBtn.disabled = true;
    addMessage("bot", "Google account connected! Ask me to find a document, email, or calendar event.");
    return;
  }
  pollForConnection(attemptsLeft - 1);
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  addMessage("user", text);
  chatInput.value = "";

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  const data = await res.json();
  addMessage("bot", data.reply, data.results, data.action);
});

refreshStatus();

// Professional UI connection indicator; does not alter authentication behavior.
(() => {
  const btn = document.getElementById("connect-btn");
  const pill = document.getElementById("connection-pill");
  if (!btn || !pill) return;
  const text = pill.querySelector(".status-text");
  const sync = () => {
    const connected = btn.dataset.connected === "true";
    pill.classList.toggle("connected", connected);
    if (text) text.textContent = connected ? "Google connected" : "Not connected";
  };
  new MutationObserver(sync).observe(btn, { attributes: true, attributeFilter: ["data-connected"] });
  sync();
})();
