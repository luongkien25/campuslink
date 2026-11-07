import os
from controls import start
from runtime import cli


def main():
    argv = start()
    # Exec giu Docker foreground; systemd quan ly signal/lifecycle, khong luu log vao RAM.
    os.execvp(argv[0], argv)


if __name__ == '__main__':
    cli(main)
