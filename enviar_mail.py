"""Envía por mail el último Panel Semanal (imagen en el cuerpo + audio adjunto)."""
import os, json, smtplib, ssl, pathlib

CARPETA = pathlib.Path("docs") / "semanal"


def main():
    usuario = os.environ.get("GMAIL_USUARIO", "").strip()
    clave = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not usuario or not clave:
        print("Falta configurar GMAIL_USUARIO o GMAIL_APP_PASSWORD: no se envía el mail.")
        return
    destinatarios = [d.strip() for d in os.environ.get("MAIL_DESTINATARIOS", "").replace(";", ",").split(",")
                     if d.strip()] or [usuario]

    from email.message import EmailMessage
    ed = json.loads((CARPETA / "ediciones.json").read_text())[0]
    f = ed["fecha"]
    panel = (CARPETA / f"panel-{f}.png").read_bytes()
    audio = (CARPETA / f"panel-{f}.mp3").read_bytes()
    pagina = os.environ.get("FEED_BASE_URL", "").rstrip("/") + "/semanal/"
    dd, mm, aa = f[8:10], f[5:7], f[:4]

    msg = EmailMessage()
    msg["Subject"] = f"Panel Semanal Toros Capital · {dd}/{mm}/{aa}"
    msg["From"] = f"Panel Semanal Toros <{usuario}>"
    msg["To"] = usuario
    msg["Bcc"] = ", ".join(destinatarios)
    msg.set_content(f"Panel semanal del {dd}/{mm}/{aa}. Van adjuntos el panel y el audio.\n\nWeb: {pagina}")
    msg.add_alternative(f"""<html><body style="font-family:Arial,sans-serif;color:#1c3b67">
<p>Hola equipo, acá está el <b>Panel Semanal</b> del {dd}/{mm}/{aa}. El audio va adjunto.</p>
<img src="cid:panel" style="max-width:100%;border-radius:8px">
<p><a href="{pagina}">Ver en la web</a></p>
</body></html>""", subtype="html")
    msg.get_payload()[1].add_related(panel, "image", "png", cid="<panel>")
    msg.add_attachment(panel, maintype="image", subtype="png", filename=f"Panel-Semanal-{f}.png")
    msg.add_attachment(audio, maintype="audio", subtype="mpeg", filename=f"Resumen-Semanal-{f}.mp3")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(usuario, clave)
        s.send_message(msg)
    print(f"Mail enviado a {len(destinatarios)} destinatario(s).")


if __name__ == "__main__":
    main()
