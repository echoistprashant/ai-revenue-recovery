import { redirect } from "next/navigation";

import { landingPathFor } from "@/lib/access";
import { readSession } from "@/lib/session-server";

/**
 * The root sends each visitor to the first module their role can open, so a `VIEWER`
 * does not land on an operations page they cannot use.
 */
export default async function Home() {
  const session = await readSession();
  redirect(session ? landingPathFor(session.role) : "/login");
}
