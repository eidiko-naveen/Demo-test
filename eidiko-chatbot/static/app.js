const $ = (id) => document.getElementById(id);

const state = {
    authenticated: false,
    busy: false
};


// ============================================================
// TOAST
// ============================================================

function toast(message) {
    const el = $("toast");

    if (!el) return;

    el.textContent = message;
    el.classList.add("show");

    clearTimeout(toast.timer);

    toast.timer = setTimeout(() => {
        el.classList.remove("show");
    }, 3500);
}


// ============================================================
// CONNECTION STATUS
// ============================================================

function setConnected(connected) {

    state.authenticated = connected;

    const dot = $("statusDot");
    const text = $("statusText");
    const connectBtn = $("connectBtn");
    const disconnectBtn = $("disconnectBtn");

    if (dot) {
        dot.classList.toggle(
            "connected",
            connected
        );
    }

    if (text) {
        text.textContent =
            connected
                ? "Google connected"
                : "Google not connected";
    }

    if (connectBtn) {

        connectBtn.disabled = false;

        if (connected) {
            connectBtn.innerHTML =
                '<span class="google-g">✓</span> Connected';
        } else {
            connectBtn.innerHTML =
                '<span class="google-g">G</span> Connect Google';
        }
    }

    if (disconnectBtn) {

        disconnectBtn.classList.toggle(
            "hidden",
            !connected
        );
    }
}


// ============================================================
// CHECK GOOGLE STATUS
// ============================================================

async function refreshStatus() {

    try {

        const response = await fetch(
            "/api/status",
            {
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error("Status request failed");
        }

        const data = await response.json();

        setConnected(
            Boolean(
                data.authenticated ||
                data.connected
            )
        );

    } catch (error) {

        state.authenticated = false;

        if ($("statusText")) {
            $("statusText").textContent =
                "Connection unavailable";
        }
    }
}


// ============================================================
// CONNECT GOOGLE
// ============================================================

async function connectGoogle() {

    const button = $("connectBtn");

    if (button) {
        button.disabled = true;
        button.innerHTML =
            "Opening Google…";
    }

    try {

        const response = await fetch(
            "/api/authorize",
            {
                cache: "no-store"
            }
        );

        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(
                data.error ||
                "Could not start Google sign-in."
            );
        }

        if (!data.authUrl) {
            throw new Error(
                "Google authorization URL was not returned."
            );
        }

        window.open(
            data.authUrl,
            "_blank",
            "noopener,noreferrer"
        );

        toast(
            "Google sign-in opened in a new tab."
        );

        if ($("statusText")) {
            $("statusText").textContent =
                "Waiting for Google approval…";
        }

        // Poll until token.json is created.
        let attempts = 0;

        const timer = setInterval(
            async () => {

                attempts++;

                await refreshStatus();

                if (
                    state.authenticated ||
                    attempts >= 60
                ) {

                    clearInterval(timer);

                    if (!state.authenticated) {

                        if (button) {
                            button.disabled = false;
                            button.innerHTML =
                                '<span class="google-g">G</span> Connect Google';
                        }

                        toast(
                            "Google connection was not completed."
                        );
                    }
                }
            },
            2000
        );

    } catch (error) {

        if (button) {
            button.disabled = false;
            button.innerHTML =
                '<span class="google-g">G</span> Connect Google';
        }

        toast(
            error.message ||
            "Could not connect Google."
        );
    }
}


// ============================================================
// DISCONNECT
// ============================================================

async function disconnectGoogle() {

    try {

        const response = await fetch(
            "/api/disconnect",
            {
                method: "POST"
            }
        );

        const data = await response.json();

        if (!response.ok || !data.ok) {
            throw new Error(
                data.error ||
                "Could not disconnect Google."
            );
        }

        setConnected(false);

        toast(
            "Google account disconnected."
        );

    } catch (error) {

        toast(
            error.message ||
            "Could not disconnect Google."
        );
    }
}


// ============================================================
// HTML ESCAPING
// ============================================================

function escapeHtml(value) {

    return String(
        value ?? ""
    ).replace(
        /[&<>"']/g,
        character => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        })[character]
    );
}


// ============================================================
// RESULT HELPERS
// ============================================================

function sourceClass(source) {

    if (source === "calendar") {
        return "calendar";
    }

    if (source === "drive") {
        return "drive";
    }

    return "gmail";
}


function sourceLabel(source) {

    if (source === "calendar") {
        return "Calendar";
    }

    if (source === "drive") {
        return "Drive";
    }

    return "Gmail";
}


function sourceLetter(source) {

    if (source === "calendar") {
        return "C";
    }

    if (source === "drive") {
        return "D";
    }

    return "M";
}


// ============================================================
// CHAT MESSAGES
// ============================================================

function addMessage(role, text) {

    const wrapper =
        document.createElement("div");

    wrapper.className =
        `message ${role}`;

    const avatar =
        document.createElement("div");

    avatar.className =
        `avatar ${role === "user" ? "me" : "ai"}`;

    avatar.textContent =
        role === "user"
            ? "You"
            : "E";

    const bubble =
        document.createElement("div");

    bubble.className = "bubble";

    bubble.textContent =
        text || "";

    if (role === "user") {

        wrapper.append(
            bubble,
            avatar
        );

    } else {

        wrapper.append(
            avatar,
            bubble
        );
    }

    $("messages").appendChild(
        wrapper
    );

    scrollWorkspace();
}


function typing() {

    const wrapper =
        document.createElement("div");

    wrapper.className = "message";
    wrapper.id = "typingMessage";

    wrapper.innerHTML = `
        <div class="avatar ai">E</div>
        <div class="bubble">
            <div class="typing">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;

    $("messages").appendChild(
        wrapper
    );

    scrollWorkspace();
}


// ============================================================
// RESULTS
// ============================================================

function addResults(results) {

    if (
        !Array.isArray(results) ||
        results.length === 0
    ) {
        return;
    }

    const grid =
        document.createElement("div");

    grid.className =
        "result-grid";

    results.forEach(result => {

        const source =
            sourceClass(
                result.source
            );

        const card =
            document.createElement("article");

        card.className =
            "result-card";

        let actions = "";

        if (result.link) {

            actions += `
                <a
                    class="result-link"
                    href="${escapeHtml(result.link)}"
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    Open ${sourceLabel(result.source)} ↗
                </a>
            `;
        }

        if (
            Array.isArray(
                result.attachments
            )
        ) {

            result.attachments.forEach(
                attachment => {

                    if (
                        attachment.download_url
                    ) {

                        actions += `
                            <a
                                class="result-link"
                                href="${escapeHtml(
                                    attachment.download_url
                                )}"
                            >
                                ↓ ${escapeHtml(
                                    attachment.filename ||
                                    "Attachment"
                                )}
                            </a>
                        `;
                    }
                }
            );
        }

        card.innerHTML = `
            <div class="result-top">

                <div class="result-source ${source}">
                    ${sourceLetter(result.source)}
                </div>

                <div class="result-title">
                    ${escapeHtml(
                        result.title ||
                        "Untitled"
                    )}
                </div>

            </div>

            <div class="result-meta">
                ${escapeHtml(
                    result.meta || ""
                )}

                ${
                    result.meta && result.date
                        ? " • "
                        : ""
                }

                ${escapeHtml(
                    result.date || ""
                )}
            </div>

            <div class="result-actions">
                ${actions}
            </div>
        `;

        grid.appendChild(card);
    });

    $("messages").appendChild(
        grid
    );

    scrollWorkspace();
}


// ============================================================
// SCROLL
// ============================================================

function scrollWorkspace() {

    requestAnimationFrame(() => {

        const workspace =
            $("workspace");

        if (workspace) {

            workspace.scrollTop =
                workspace.scrollHeight;
        }

    });
}


// ============================================================
// SEND MESSAGE
// ============================================================

async function sendMessage(
    override = null
) {

    if (state.busy) {
        return;
    }

    const input =
        $("messageInput");

    const message =
        (
            override ??
            input.value
        ).trim();

    if (!message) {
        return;
    }

    if (!state.authenticated) {

        toast(
            "Connect your Google account first."
        );

        return;
    }

    $("hero").classList.add(
        "hidden"
    );

    $("chatPanel").classList.remove(
        "hidden"
    );

    input.value = "";

    addMessage(
        "user",
        message
    );

    typing();

    state.busy = true;

    $("sendBtn").disabled = true;

    try {

        const response =
            await fetch(
                "/api/chat",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        message
                    })
                }
            );

        const data =
            await response.json();

        $("typingMessage")?.remove();

        if (!response.ok) {

            throw new Error(
                data.reply ||
                data.error ||
                "Search failed."
            );
        }

        addMessage(
            "assistant",
            data.reply ||
            "I couldn't find a useful match."
        );

        addResults(
            data.results || []
        );

    } catch (error) {

        $("typingMessage")?.remove();

        addMessage(
            "assistant",
            error.message ||
            "Something went wrong."
        );

    } finally {

        state.busy = false;

        $("sendBtn").disabled =
            false;

        input.focus();
    }
}


// ============================================================
// NEW CHAT
// ============================================================

function newChat() {

    $("messages").innerHTML = "";

    $("chatPanel").classList.add(
        "hidden"
    );

    $("hero").classList.remove(
        "hidden"
    );

    $("messageInput").focus();
}


// ============================================================
// EVENTS
// ============================================================

$("connectBtn").addEventListener(
    "click",
    connectGoogle
);

$("disconnectBtn").addEventListener(
    "click",
    disconnectGoogle
);

$("newChatBtn").addEventListener(
    "click",
    newChat
);

$("chatForm").addEventListener(
    "submit",
    event => {
        event.preventDefault();
        sendMessage();
    }
);

document
    .querySelectorAll(".quick-card")
    .forEach(card => {

        card.addEventListener(
            "click",
            () => {
                sendMessage(
                    card.dataset.query
                );
            }
        );

    });

$("messageInput").addEventListener(
    "keydown",
    event => {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            $("chatForm").requestSubmit();
        }

    }
);


// ============================================================
// START
// ============================================================

refreshStatus();

setInterval(
    refreshStatus,
    5000
);