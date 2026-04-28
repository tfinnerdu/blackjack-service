// Captures the browser's deferred PWA install prompt so we can show our
// own 'Install' button. Chrome / Edge / Samsung Internet emit a
// 'beforeinstallprompt' event we can stash + replay on user click.
// Safari (iOS) doesn't expose programmatic install — caller handles
// that with an instructional fallback.

import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

export function useInstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    function onBeforeInstall(e: Event) {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
    }
    function onInstalled() {
      setInstalled(true);
      setDeferred(null);
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);

    // Detect already-running-as-installed-PWA so we don't show the prompt.
    const standalone = window.matchMedia?.("(display-mode: standalone)")?.matches;
    const iosStandalone = (window.navigator as any).standalone === true;
    if (standalone || iosStandalone) setInstalled(true);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  async function trigger(): Promise<"accepted" | "dismissed" | "unavailable"> {
    if (!deferred) return "unavailable";
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted") {
      setInstalled(true);
      setDeferred(null);
    }
    return outcome;
  }

  function isIOS(): boolean {
    const ua = window.navigator.userAgent;
    return /iPad|iPhone|iPod/.test(ua) && !(window as any).MSStream;
  }

  return {
    available: !!deferred,
    installed,
    isIOS: isIOS(),
    trigger,
  };
}
