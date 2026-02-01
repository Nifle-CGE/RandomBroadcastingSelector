import { drizzle } from 'drizzle-orm/d1';
import { drizzle as drizzleLibSQL } from 'drizzle-orm/libsql';
import { createClient } from '@libsql/client';
import { dev } from '$app/environment';
import { env } from '$env/dynamic/private';

export function getDB(platform: App.Platform | undefined) {
    if (!dev && platform?.env.DB) {
        // Production: Use Cloudflare D1
        return drizzle(platform.env.DB);
    } else {
        // Development: Use LibSQL with local.db
        const client = createClient({ url: env.DB_FILE_NAME });
        return drizzleLibSQL(client);
    }
}
