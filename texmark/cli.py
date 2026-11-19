"""The ``texmark`` command: ``texmark sync ...`` (texmark.sync), ``texmark
schema`` (texmark.schema), else the build (texmark.build). The build module
is only imported for a build, so that ``texmark sync``, which runs on each
click in an editor, starts fast."""
import os
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'sync' and not os.path.exists('sync'):
        from texmark.sync import main as sync_main
        sys.exit(sync_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == 'schema' and not os.path.exists('schema'):
        from texmark.schema import main as schema_main
        sys.exit(schema_main(sys.argv[2:]))
    from texmark.build import main as build_main
    build_main()


if __name__ == '__main__':
    main()
