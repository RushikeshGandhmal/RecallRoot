"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface AsyncResource<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refresh: () => Promise<T | null>;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

export function useAsyncResource<T>(loader: () => Promise<T>): AsyncResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await loader();
      if (id === requestId.current) setData(result);
      return result;
    } catch (caught) {
      const nextError = caught instanceof Error ? caught : new Error("Unexpected request failure");
      if (id === requestId.current) setError(nextError);
      return null;
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void refresh(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      requestId.current += 1;
    };
  }, [refresh]);

  return { data, error, loading, refresh, setData };
}
