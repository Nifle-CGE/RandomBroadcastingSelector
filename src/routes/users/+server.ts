import type { RequestHandler } from '@sveltejs/kit';
import { users } from '$lib/server/db/schema';
import { getDB } from '$lib/server/db';

export const GET: RequestHandler = async ({ platform }) => {
    const db = getDB(platform);
    const result = await db.select().from(users).all();
    return new Response(JSON.stringify(result), {
        headers: { 'Content-Type': 'application/json' }
    });
};

export const POST: RequestHandler = async ({ platform, request }) => {
    const db = getDB(platform);
    const { name, age, email } = await request.json();
    const result = await db.insert(users).values({ name, age, email }).returning().get();
    return new Response(JSON.stringify(result), {
        headers: { 'Content-Type': 'application/json' }
    });
}
