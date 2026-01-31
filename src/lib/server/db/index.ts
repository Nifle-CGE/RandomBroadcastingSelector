import { drizzle } from 'drizzle-orm/d1';

export interface Env {
    DB: D1Database;
}
export default {
    async fetch(request: Request, env: Env) {
        const db = drizzle(env.DB);
        const result = await db.select().from(users).all()
        return Response.json(result);
    },
};
