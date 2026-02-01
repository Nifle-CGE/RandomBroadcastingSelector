import { drizzle } from 'drizzle-orm/d1';
import { drizzle as drizzleLibSQL } from 'drizzle-orm/libsql';
import { createClient } from '@libsql/client';
import { DB_FILE_NAME } from '$env/static/private';


export function getDB(platform: App.Platform | undefined) {
    if (process.env.NODE_ENV === 'production' && platform?.env.DB) {
        // Production: Use Cloudflare D1
        return drizzle(platform.env.DB);
    } else {
        // Development: Use LibSQL with local.db
        const client = createClient({ url: DB_FILE_NAME });
        return drizzleLibSQL(client);
    }
}
