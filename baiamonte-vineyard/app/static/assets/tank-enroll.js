(function () {
  const code = document.getElementById("pairingCode");
  const status = document.getElementById("enrollmentStatus");
  const gateway = window.location.pathname.startsWith("/api/baiamonte_labels/") ? "/api/baiamonte_labels" : "";
  const displayPath = gateway ? window.location.pathname.slice(gateway.length) : window.location.pathname;
  const apiUrl = `${gateway}/api${displayPath}${window.location.search}`;
  const publicDestination = (value) => gateway && String(value || "").startsWith("/") ? `${gateway}${value}` : value;
  async function poll() {
    try {
      const response = await fetch(apiUrl, {cache: "no-store", credentials: "include", referrerPolicy: "no-referrer"});
      if (!response.ok) throw new Error("Enrollment service unavailable");
      const payload = await response.json();
      if (payload.status === "approved") {
        status.textContent = payload.device_role === "ipad" ? "Approved · opening Vineyard Operations" : "Approved · opening tank label";
        window.location.replace(publicDestination(payload.destination_url || payload.kiosk_url));
        return;
      }
      if (payload.status === "rejected") {
        status.textContent = payload.message || "Enrollment declined";
        code.textContent = "DECLINED";
        return;
      }
      code.textContent = payload.pairing_code || "———";
      status.textContent = "Enter this code in Vineyard Operations";
    } catch (_) {
      status.textContent = "Waiting for the enrollment service · retrying";
    }
    window.setTimeout(poll, 5000);
  }
  poll();
}());
