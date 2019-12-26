from util.git_mirror import MirrorGitlab


if __name__ == "__main__":
    mirror = MirrorGitlab("oa", "aws")
    mirror.start_sync()
