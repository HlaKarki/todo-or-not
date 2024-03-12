import os
import subprocess
import sys

from typer import Option, run
from typing import List, Optional
from typing_extensions import Annotated

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = _script_dir
_todo_ignore_file = os.path.join(_project_dir, ".todo-ignore")


def find_lines(filename: str, ignore_flag: str, *args) -> list[tuple[str, int, [str]]]:
    """
    Finds and returns each line of a file that contains a key
    :param filename: File to open() read-only
    :param args: Keys to check each line for
    :return: List of lines of text and their line number that contain at least one key and the keys each contains
    """
    output = []

    with open(filename, 'r', encoding="UTF-8") as file:
        line_number = 0
        lines = file.readlines()

        for _line in lines:
            _found_keys = []
            for key in args:
                if key.lower() in _line.lower() and ignore_flag.lower() not in _line.lower():
                    _found_keys.append(key)

            if len(_found_keys) > 0:
                _hit = (_line, line_number, _found_keys)
                output.append(_hit)

            line_number += 1

    return output


def _print_todo_found(target, hits, silent=False):
    _output = []
    for hit in hits:
        header = ", ".join(hit[2])
        header = f"[{header}]".upper()
        _pad = 16 - len(header)
        padding = " " * _pad
        header = header + padding

        location = os.path.relpath(target, _project_dir)
        location = f"{location}:{hit[1]}"
        _pad = 16 - len(location)
        padding = " " * _pad
        location = location + padding

        if not silent:
            print(f"{header} - {location} - {hit[0].strip()}", file=sys.stderr)
        _printable_hit = (header, location, hit[0].strip())
        _output.append(_printable_hit)
    return _output


def update_todo_ignore(other_file_names, target_file):
    target_file.write('\n')
    for file_name in other_file_names:
        with open(file_name, "r") as file:
            target_file.writelines(file.read())


def _generate_issues(printables: tuple[str, str, str]):
    output = []

    for printable in printables:
        title = f"{printable[0]} - {printable[1]}"

        repo_uri = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY')}"
        github_ref = os.environ.get('GITHUB_REF').split("/")
        reference = printable[1].split(":")[0]

        reference_uri = f"{repo_uri}/blob/{github_ref[1:]}/{reference}"

        triggered_by = os.environ.get("GITHUB_TRIGGERING_ACTOR")

        body = (f"Reference: <a href=\"{reference_uri}\">{printable[1]}</a>\n\n"
                f"{printable[1]}")

        owner, repo = os.environ.get('GITHUB_REPOSITORY').split("/")

        _output = subprocess.check_output(
            [
                "gh", "api",
                "--method", "POST",
                "-H", "Accept: application/vnd.github+json",
                "-H", "X-GitHub-Api-Version: 2022-11-28",
                f"/repos/{owner}/{repo}/issues",
                "-f", f"title={title}",
                "-f", f"body={body}",
                "-f", f"assignees[]={triggered_by}"
                ]
        )

        output.append(_output)

    return output


def main(
        mode: str = "print",
        silent: bool = False,
        force: bool = False,
        ni: Annotated[
            Optional[List[str]], Option(help="Copy the contents of other files into a new .todo-ignore")] = None,
        xi: Annotated[
            Optional[List[str]], Option(help="Copy the contents of other files into an existing .todo-ignore")] = None
):
    targets = []
    ignored_files = []
    ignored_dirs = []

    if (len(ni) > 0) and (len(xi) > 0):
        print("FATAL: Cannot specify both --ni and --ci.", file=sys.stderr)
        exit(1)
    elif (len(ni) > 0) or (len(xi) > 0):
        if force:
            _option = "--ni" if (len(ni) > len(xi)) else "--ci"
            print("WARNING: --force will ignore the contents of the .todo-ignore generated when you specified",
                  _option,
                  file=sys.stderr)

        mode = "a+" if (len(ni) > len(xi)) else "w"
        _list = ni if (len(ni) > len(xi)) else xi

        with open(os.path.join(_project_dir, ".todo-ignore"), mode, encoding="UTF-8") as new_todo_ignore_file:
            update_todo_ignore(_list, new_todo_ignore_file)

    if not force:
        try:
            with open(_todo_ignore_file, 'r'):
                pass
        except FileNotFoundError:
            print(
                "FATAL: .todo-ignore NOT FOUND! use -i to copy another .ignore OR "
                "--force to run without a .todo-ignore (NOT RECOMMENDED)",
                file=sys.stderr)
            exit(1)

        with open(_todo_ignore_file, 'r') as _ignore:
            for line in _ignore.readlines():
                if not line.startswith("#") and len(line) > 1:
                    if line.endswith('\n'):
                        cur_name = line[:-1]
                    else:
                        cur_name = line

                    cur_path = os.path.join(_project_dir, cur_name)

                    if os.path.isfile(cur_path):
                        ignored_files.append(cur_path)

                    if os.path.isdir(cur_path):
                        ignored_dirs.append(cur_path)

            # Ignore the .todo-ignore itself
            ignored_files.append(os.path.abspath(_ignore.name))
    else:
        print("WARNING: Running without a .todo-ignore (NOT RECOMMENDED), [Ctrl + C] to cancel", file=sys.stderr)

    # Ignore this script
    ignored_files.append(__file__)

    _walk = os.walk(_project_dir)

    for (dirpath, dirnames, filenames) in _walk:
        # Break if an ignored dir
        _ignore_this_dir = False

        for _dir in ignored_dirs:
            if os.path.samefile(dirpath, _dir):
                _ignore_this_dir = True
        if _ignore_this_dir:
            break

        for _file in filenames:
            current = os.path.join(dirpath, _file)

            for i in ignored_files:
                if os.path.samefile(i, current):
                    current = None
                    break

            if current is not None:
                targets.append(current)

    #############################################
    # Handle output
    #############################################

    fail = False
    for target in targets:
        hits = find_lines(target, "@todoon", "todo", "fixme")

        if len(hits) > 0:
            fail = True

            # Print the hits if the issue option is not specified, if it is then be silent and generate issues
            _printable_hits = _print_todo_found(target, hits, mode.lower() == "issue")

            if mode.lower() == "issue":
                _generate_issues(_printable_hits)

    if fail:
        print("\n######\nTODO and FIXME check failed, please address the above and try again.\n######\n")
        if not silent:
            exit(1)
    else:
        print("\n######\nTODO and FIXME check passed!\n######\n")


if __name__ == "__main__":
    run(main)
