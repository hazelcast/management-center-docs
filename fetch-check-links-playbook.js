const [githubRepo, githubBaseBranch] = process.argv.slice(-2);

if (!githubRepo || !githubBaseBranch) {
	throw new Error('GitHub repository name and base branch should be passed as arguments');
}

console.log(githubRepo, githubBaseBranch);
