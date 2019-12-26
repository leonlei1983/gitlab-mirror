import os
import re
import gitlab
import logging

from logging import handlers
from datetime import datetime
from gitlab.exceptions import GitlabCreateError

from util.common import command_exec
from util.notification import Notification


class MirrorGitlab:
    _groups_src_objs_id = None
    _groups_dst_objs_full_path = None
    _groups_count = 0

    _projects_src_objs_id = None
    _projects_dst_objs_namespace_path = None
    _projects_count = 0

    def __init__(self, src_id, dst_id, config_path="config.cfg"):
        self._gl_src = gitlab.Gitlab.from_config(src_id, [config_path])
        self._gl_dst = gitlab.Gitlab.from_config(dst_id, [config_path])
        self._working_dir = "working"
        self._logger = self._create_logger()
        self._notify = Notification(config_path)

    def _create_logger(self, log_level=logging.DEBUG):
        formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        logger = logging.getLogger(__name__)
        logger.setLevel(log_level)

        # log to stdout
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # log to file
        handler = handlers.RotatingFileHandler("./log/app.log", maxBytes=20 * 1024 * 1024, backupCount=7)
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def _create_project(self, projects_src, group_dst):
        create_attrs = dict(
            name=projects_src.name,
            path=projects_src.path,
            namespace_id=group_dst.id,
            description=projects_src.description,
            visibility=projects_src.visibility,
        )
        try:
            projects_dst = self._gl_dst.projects.create(create_attrs)
            projects_dst.save()
        except GitlabCreateError as e:
            self._logger.error("fail to create project: %s (%d)", projects_src.path_with_namespace, projects_src.id)
            self._logger.error("create_attrs: %s", create_attrs)
            self._logger.error(e)
            self._notify.send_message("fail to create project: %s (%d)\ncreate_attrs: %s\n%s" % (
                projects_src.path_with_namespace, projects_src.id, create_attrs, e,
            ))
            raise e

        self._logger.info("create project: %s (%d)", projects_dst.path_with_namespace, projects_dst.id)
        return projects_dst

    def _sync_project(self, project_src, project_dst):
        regex = r"^(?:https?://[^/]+)(.*)"
        matcher = re.match(regex, project_src.http_url_to_repo)
        src_url = project_src.manager.gitlab.url + matcher.group(1)
        repo_path = self._working_dir + matcher.group(1)

        matcher = re.match(regex, project_dst.http_url_to_repo)
        dst_url = project_dst.manager.gitlab.url + matcher.group(1)

        regex = r"^(https?://)(.*)"
        matcher = re.match(regex, src_url)
        src_url = "{0}oauth2:{2}@{1}".format(*matcher.groups(), project_src.manager.gitlab.private_token)

        matcher = re.match(regex, dst_url)
        dst_url = "{0}oauth2:{2}@{1}".format(*matcher.groups(), project_dst.manager.gitlab.private_token)

        # clone and push
        if os.path.isdir(repo_path):
            if not command_exec("git fetch -p origin", cwd=repo_path):
                self._logger.error("fail to fetch project: %s (%d)", project_src.path_with_namespace, project_src.id)
                self._notify.send_message("fail to fetch project: %s (%d)" % (
                    project_src.path_with_namespace, project_src.id,
                ))
                return
        else:
            repo_dirpath = os.path.dirname(repo_path)
            os.makedirs(repo_dirpath, exist_ok=True)
            if not command_exec("git clone --mirror %s" % src_url, cwd=repo_dirpath):
                self._logger.error("fail to clone project: %s (%d)", project_src.path_with_namespace, project_src.id)
                self._notify.send_message("fail to clone project: %s (%d)" % (
                    project_src.path_with_namespace, project_src.id,
                ))
                return

        # add git remote mirror url
        if not command_exec("git remote show aws-git", cwd=repo_path):
            if not command_exec("git remote add --mirror=push aws-git %s" % dst_url, cwd=repo_path):
                self._logger.error("fail to add remote mirror url: %s", dst_url)
                self._notify.send_message("fail to add remote mirror url: %s" % dst_url)
                return

        # git push
        if command_exec("git push --mirror aws-git", cwd=repo_path):
            self._logger.info("finish sync project: %s (%d)", project_src.path_with_namespace, project_src.id)
        else:
            self._logger.error("fail to sync project: %s (%d)", project_src.path_with_namespace, project_src.id)
            self._notify.send_message("fail to sync project: %s (%d)" % (
                project_src.path_with_namespace, project_src.id,
            ))

    def _mirror_projects(self, group_src, group_dst):
        projects_src = group_src.projects.list(all=True)
        projects_dst = group_dst.projects.list(all=True)
        self._projects_count += len(projects_src)
        if len(projects_src) == 0:
            return

        # create dictionary by namespace path
        self._projects_src_objs_id = dict(map(lambda p: (p.id, p), projects_src))
        self._projects_dst_objs_namespace_path = dict(map(lambda p: (p.path_with_namespace, p), projects_dst))

        for project_src in projects_src:
            project_dst = self._projects_dst_objs_namespace_path.get(project_src.path_with_namespace)
            if not project_dst:
                project_dst = self._create_project(project_src, group_dst)
            self._sync_project(project_src, project_dst)

    def _create_group(self, group_src):
        group_dst = self._groups_dst_objs_full_path.get(group_src.full_path)
        if group_dst is not None:
            return group_dst

        create_attrs = dict(
            name=group_src.name,
            path=group_src.path,
            description=group_src.description,
            visibility=group_src.visibility,
            lfs_enabled=group_src.lfs_enabled,
        )

        if group_src.parent_id:
            group_parent_src = self._gl_src.groups.get(group_src.parent_id)
            group_parent_dst = self._groups_dst_objs_full_path.get(group_parent_src.full_path)
            if group_parent_dst:
                group_parent_dst = self._create_group(group_parent_src)
                create_attrs["parent_id"] = group_parent_dst.id

        # create group in mirror gitlab
        try:
            group_dst = self._gl_dst.groups.create(create_attrs)
            group_dst.save()
        except GitlabCreateError as e:
            self._logger.error("fail to create group: %s (%d)", group_src.full_path, group_src.id)
            self._logger.error("create_attrs: %s", create_attrs)
            self._logger.error(e)
            self._notify.send_message("fail to create group: %s (%d)\ncreate_attrs: %s\n%s" % (
                group_src.full_path, group_src.id, create_attrs, e,
            ))
            raise e

        self._logger.info("create group: %s (%d)", group_dst.name, group_dst.id)
        return group_dst

    def _mirror_groups(self, group_name):
        groups_src = self._gl_src.groups.list(search=group_name) if group_name else self._gl_src.groups.list(all=True)
        groups_dst = self._gl_dst.groups.list(all=True)
        self._groups_count = len(groups_src)
        if len(groups_src) == 0:
            return

        # create dictionary by id or full_path
        self._groups_src_objs_id = dict(map(lambda g: (g.id, g), groups_src))
        self._groups_dst_objs_full_path = dict(map(lambda g: (g.full_path, g), groups_dst))

        for group_src in sorted(groups_src, key=lambda g: g.id):
            group_dst = self._create_group(group_src)
            self._mirror_projects(group_src, group_dst)

    def start_sync(self, group_name=None):
        if not os.path.isdir(self._working_dir):
            os.makedirs(self._working_dir)

        # reset counter
        self._groups_count = 0
        self._projects_count = 0
        date_fmt = "%Y%m%d %H%M%S"

        # mirror
        starttime = datetime.utcnow()
        self._logger.debug("start to mirror at %s", starttime.strftime(date_fmt))
        self._mirror_groups(group_name)
        endtime = datetime.utcnow()
        self._logger.info("finish to mirror at %s", endtime.strftime(date_fmt))

        # show the time cost
        delta = endtime - starttime
        self._logger.info("total cost: %d secs", delta.total_seconds())
        self._logger.info("groups count: %d", self._groups_count)
        self._logger.info("projects count: %d", self._projects_count)

        self._notify.send_message("""total cost: %d secs\ngroups count: %d\nprojects count: %d""" % (
            delta.total_seconds(),
            self._groups_count,
            self._projects_count,
        ))


