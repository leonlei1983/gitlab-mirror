import logging
import shlex
import subprocess


def command_exec(cmd, cwd=None, logger=logging.getLogger(__name__)):
    try:
        process = subprocess.Popen(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
        )

        while process.poll() is None:
            while True:
                line = process.stdout.readline().decode()
                if not line:
                    break
                logger.info(line.rstrip())

        return process.returncode == 0
    except Exception as e:
        logger.error(e)

    return False
