def pause_for_user(message="\nFinished. Press Enter to exit."):
    try:
        input(message)
    except (EOFError, KeyboardInterrupt):
        pass
