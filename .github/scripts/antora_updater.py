#!/usr/bin/env python

import os
import logging
import urllib.request
from ruamel.yaml import YAML

def fetch_antora_utils() -> None:
    branch = "DI-719-migrate-antora-1"
    target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "antora_utils.py")
    url_path = f"{os.getenv('GITHUB_REPOSITORY_OWNER')}/hz-docs/{branch}/.github/scripts/antora_utils.py"
    if not os.path.exists(target_path):
        url = f"https://raw.githubusercontent.com/{url_path}"
        urllib.request.urlretrieve(url, filename=target_path)

fetch_antora_utils()
import antora_utils as utils
logger: logging.Logger = utils.setup_logger(__name__)

ANTORA_FILE: str = "docs/antora.yml"

def process_antora(
    master_major_minor: str,
    rel_major_minor: str,
    is_main: bool,
    is_patch_release: bool = False,
    is_latest_stable_release: bool = False
) -> bool:

    yaml: YAML = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    
    with open(ANTORA_FILE, 'r+') as f:
        data = yaml.load(f)
        attrs = data['asciidoc']['attributes']
        hz_page = 'page-latest-supported-hazelcast'

        if is_main:
            attrs[hz_page] = f"{master_major_minor}-snapshot"
        else:
            # We need to account for when MC latest version changes during latest PATCH release.
            # The (next) v/branch needs to point to the current latest release. However,
            # it might already be set correctly (from previous latest PATCH run) so skip
            # update if thats the case
            if is_patch_release and is_latest_stable_release:
                current_value = attrs.get(hz_page, "")
                if current_value == rel_major_minor:
                    logger.warning(f"Skipping update - current '{hz_page}' value '{current_value}' already matches '{rel_major_minor}'")
                    return False

            attrs[hz_page] = rel_major_minor

        f.seek(0)
        yaml.dump(data, f)
        f.truncate()

    return True

def update_release(
    release_ver: str,
    rel_major_minor: str,
    master_major_minor: str,
    mc_major_minor: str,
    is_patch_release: bool = False,
    is_latest_stable_release: bool = False
) -> None:

    target_base = f"v/{mc_major_minor}"
    update_branch: str = utils.checkout_branch("antora", target_base)
    
    should_proceed = process_antora(
        master_major_minor=master_major_minor,
        rel_major_minor=rel_major_minor,
        is_main=False,
        is_patch_release=is_patch_release,
        is_latest_stable_release=is_latest_stable_release
    )
    
    if should_proceed:
        utils.commit_changes(target_base, release_ver, [ANTORA_FILE], update_branch)
        utils.create_github_pr(target_base, update_branch, release_ver)

def update_main(
    master_version: str,
    master_major_minor: str
) -> None:

    target_base: str = "main"
    update_branch: str = utils.checkout_branch("antora", target_base)
    
    process_antora(
        master_major_minor=master_major_minor,
        rel_major_minor="",
        is_main=True
    )
    
    utils.commit_changes(target_base, master_version, [ANTORA_FILE], update_branch)
    utils.create_github_pr(target_base, update_branch, master_version)

def update(
    release_ver: str,
    rel_major_minor: str,
    master_version: str,
    master_major_minor: str,
    mc_major_minor: str,
    is_latest_stable_release: str,
    is_rel_major_minor: str,
    is_patch_release: str
) -> None:

    is_patch: bool = is_patch_release == "true"
    is_rel_maj_min: bool = is_rel_major_minor == "true"
    is_latest_stable: bool = is_latest_stable_release == "true"

    if is_rel_maj_min:
        update_main(
            master_version=master_version,
            master_major_minor=master_major_minor
        )

    if is_rel_maj_min or (is_patch and is_latest_stable):
        update_release(
            release_ver=release_ver,
            rel_major_minor=rel_major_minor,
            master_major_minor=master_major_minor,
            mc_major_minor=mc_major_minor,
            is_patch_release=is_patch,
            is_latest_stable_release=is_latest_stable
        )
    else:
        logger.info("Skip 'antora.yml' updates for BETA or PATCH (non latest) release")

def merge_pull_requests(
    is_rel_major_minor: str,
    is_patch_release: str,
    is_latest_stable_release: str,
    release_version: str,
    master_version: str,
    mc_major_minor: str
) -> None:

    is_patch: bool = is_patch_release == "true"
    is_rel_maj_min: bool = is_rel_major_minor == "true"
    is_latest_stable: bool = is_latest_stable_release == "true"

    if is_rel_maj_min:
        utils.merge_github_pr("main", master_version)

    if is_rel_maj_min or (is_patch and is_latest_stable):
        utils.merge_github_pr(
            f"v/{mc_major_minor}",
            release_version,
            fail_on_missing=is_rel_maj_min
        )
    else:
        logger.info("Skip 'antora.yml' updates for BETA or PATCH (non latest) release")
