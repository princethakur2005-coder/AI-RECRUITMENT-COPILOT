import { useEffect } from "react";
import { useRouter } from "next/router";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    void router.replace(token ? "/dashboard" : "/login");
  }, [router]);

  return null;
}
