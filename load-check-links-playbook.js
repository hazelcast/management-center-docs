const [githubRepo, githubBaseBranch] = process.argv.slice(-2);

if (githubRepo.endsWith('.js') || githubBaseBranch.endsWith('.js')) {
	throw new Error('GitHub repository name and base branch should be passed as arguments');
}

console.log('Repository name: ', githubRepo);
console.log('Base branch: ', githubBaseBranch);

// 1. Load and parse local antora-playbook.yml
// 2. Load and parse global antora-playbook.yml's content.sources
// 3. Modify global content.sources
// 		-
// 4. Replace local content.sources with the modified content.sources
