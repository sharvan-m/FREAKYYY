# Pairing your phone and laptop

1. **Laptop:** in Freakyyy, choose **Add device** (Devices panel, the tray menu, or say "pair my phone"). A QR code appears; it works once and expires after 5 minutes.
2. **Phone:** Freakyyy → **Devices** → **Scan pairing code**, and point the camera at the laptop screen.
   - No camera? On the laptop, press *Copy pairing link* and send it to the phone (chat, email). Tapping a `freakyyylink://pair…` link opens Freakyyy and starts pairing. You can also paste it into the field on the Devices screen.
3. **Both screens now show a 6-digit code.** The phone computes its code on its own, so if the two match, you're talking to *your* laptop.
4. Tap **Codes match — pair** on the phone. On the laptop, press **Pair**, or just say **"yes"**.
5. Done. The phone shows **CONNECTED** and the laptop shows **PHONE · <name>**. From now on the phone reconnects automatically whenever both are on the same network. The phone shows an ongoing "Freakyyy Link" notification while it's connected.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Laptop not reachable" | Same Wi-Fi? Is Freakyyy running on the laptop? Did you allow Freakyyy through Windows Firewall on **Private** networks? Is the Wi-Fi profile set to *Private* in Windows? |
| "This pairing code expired" | Create a new one on the laptop. Codes last 5 minutes and work once. |
| "Security check failed: the codes don't match" | Pairing was stopped on purpose. Try again on a network you trust. |
| "The laptop no longer recognises this phone" | The laptop removed the pairing. Pair again. |
| Laptop says your phone is offline | Open Freakyyy on the phone once. Check that the Freakyyy Link notification is there. Some phones (Vivo included) kill background services: set Freakyyy's battery usage to *Unrestricted*. |

**Removing a device:** laptop Settings → Devices → *Remove selected*, or phone Devices → *Remove laptop*. Either side deletes its key, and the other side's next login fails.
