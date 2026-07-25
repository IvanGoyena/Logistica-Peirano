from __future__ import annotations

import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st


def _normalizar_correos(
    correos: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    """
    Convierte uno o varios correos en una lista limpia.
    """

    if correos is None:
        return []

    if isinstance(correos, str):
        correos = [correos]

    return [
        str(correo).strip()
        for correo in correos
        if str(correo).strip()
    ]


def enviar_mail(
    destinatario: str | list[str],
    asunto: str,
    cuerpo_html: str,
    copia: str | list[str] | None = None,
) -> dict[str, object]:
    """
    Envía un correo mediante Gmail SMTP.
    """

    destinatarios = _normalizar_correos(
        destinatario
    )

    copias = _normalizar_correos(
        copia
    )

    if not destinatarios:
        raise ValueError(
            "Debe indicarse al menos un destinatario."
        )

    try:
        usuario = str(
            st.secrets["MAIL_USUARIO"]
        ).strip()

        password = str(
            st.secrets["MAIL_PASSWORD"]
        ).replace(" ", "").strip()

    except KeyError as error:
        raise RuntimeError(
            "Faltan MAIL_USUARIO o MAIL_PASSWORD "
            "en .streamlit/secrets.toml."
        ) from error

    mensaje = MIMEMultipart("alternative")

    mensaje["From"] = usuario
    mensaje["To"] = ", ".join(
        destinatarios
    )

    if copias:
        mensaje["Cc"] = ", ".join(
            copias
        )

    mensaje["Subject"] = asunto

    mensaje.attach(
        MIMEText(
            cuerpo_html,
            "html",
            "utf-8",
        )
    )

    receptores = list(
        dict.fromkeys(
            destinatarios + copias
        )
    )

    try:
        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=20,
        ) as servidor:

            servidor.ehlo()
            servidor.starttls()
            servidor.ehlo()

            servidor.login(
                usuario,
                password,
            )

            servidor.sendmail(
                usuario,
                receptores,
                mensaje.as_string(),
            )

    except smtplib.SMTPAuthenticationError as error:
        raise RuntimeError(
            "Gmail rechazó el acceso. Revisá el usuario "
            "y la contraseña de aplicación."
        ) from error

    except Exception as error:
        raise RuntimeError(
            f"No se pudo enviar el correo: {error}"
        ) from error

    return {
        "ok": True,
        "destinatarios": destinatarios,
        "copias": copias,
        "mensaje": "Correo enviado correctamente.",
    }