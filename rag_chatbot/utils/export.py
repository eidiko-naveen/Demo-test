def transcript_markdown(
    messages,
):

    lines = [
        "# Enterprise RAG Conversation",
        "",
    ]

    for message in messages:

        lines.append(
            f"## {message['role'].title()}"
        )

        lines.append("")

        lines.append(
            message["content"]
        )

        lines.append("")

    return "\n".join(lines)