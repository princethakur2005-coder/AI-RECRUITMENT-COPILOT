import { useEffect } from "react";
import { useRouter } from "next/router";
import { getAccessToken, getAuthPrincipal } from "../lib/api";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = getAccessToken();
    const principal = getAuthPrincipal();
    if (!token) {
      void router.replace("/login");
      return;
    }
    void router.replace(principal === "candidate" ? "/candidate-portal" : "/dashboard");
  }, [router]);

  return null;
}
