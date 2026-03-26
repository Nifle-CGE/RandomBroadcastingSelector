# RandomBroadcastingSelector

## How-To

### Drizzle

To push the database schema to the dev database, run:

```sh
bunx drizzle-kit push --config drizzle-dev.config.ts
```

To push the database schema to the production database, run:

```sh
bunx drizzle-kit push
```

## sv

Everything you need to build a Svelte project, powered by [`sv`](https://github.com/sveltejs/cli).

### Creating a project

If you're seeing this, you've probably already done this step. Congrats!

```sh
# create a new project
bunx sv create my-app
```

To recreate this project with the same configuration:

```sh
# recreate this project
bunx sv create --template minimal --types ts --add prettier eslint tailwindcss="plugins:none" sveltekit-adapter="adapter:cloudflare+cfTarget:workers" drizzle="database:sqlite+sqlite:libsql" paraglide="languageTags:fr, en+demo:no" mcp="ide:vscode+setup:remote" --install bun ./
```

### Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
bun run dev

# or start the server and open the app in a new browser tab
bun run dev -- --open
```

### Building

To create a production version of your app:

```sh
bun run build
```

You can preview the production build with `npm run preview`.

> To deploy your app, you may need to install an [adapter](https://svelte.dev/docs/kit/adapters) for your target environment.
