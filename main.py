from hawk.main import run


if __name__ == "__main__":
    import sys

    task = " ".join(sys.argv[1:]) or "open notepad and type hello world"
    run(task)
