import { useState, useEffect } from 'react';

interface GeolocationState {
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  error: string | null;
  loading: boolean;
}

interface LocationContext {
  latitude: number;
  longitude: number;
  accuracy: number;
}

export const useGeolocation = (enableHighAccuracy: boolean = true, delayMs: number = 1500) => {
  const [location, setLocation] = useState<GeolocationState>({
    latitude: null,
    longitude: null,
    accuracy: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let watchId: number | undefined;
    let timeoutId: NodeJS.Timeout;

    if (!navigator.geolocation) {
      setLocation({
        latitude: null,
        longitude: null,
        accuracy: null,
        error: 'Geolocation is not supported by this browser.',
        loading: false,
      });
      return;
    }

    const handleSuccess = (position: GeolocationPosition) => {
      setLocation({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
        error: null,
        loading: false,
      });
    };

    const handleError = (error: GeolocationPositionError) => {
      let errorMessage = 'An unknown error occurred.';
      switch (error.code) {
        case error.PERMISSION_DENIED:
          errorMessage = 'User denied the request for Geolocation.';
          break;
        case error.POSITION_UNAVAILABLE:
          errorMessage = 'Location information is unavailable.';
          break;
        case error.TIMEOUT:
          errorMessage = 'The request to get user location timed out.';
          break;
      }

      setLocation({
        latitude: null,
        longitude: null,
        accuracy: null,
        error: errorMessage,
        loading: false,
      });
    };

    const requestLocation = () => {
      const options: PositionOptions = {
        enableHighAccuracy,
        timeout: 10000,
        maximumAge: 300000, // 5 minutes
      };

      // Get initial position
      navigator.geolocation.getCurrentPosition(handleSuccess, handleError, options);

      // Watch position changes (optional for future use)
      watchId = navigator.geolocation.watchPosition(handleSuccess, handleError, options);
    };

    // Add delay before requesting location permission
    timeoutId = setTimeout(requestLocation, delayMs);

    return () => {
      if (watchId) {
        navigator.geolocation.clearWatch(watchId);
      }
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [enableHighAccuracy, delayMs]);

  const getLocationContext = (): LocationContext | null => {
    if (location.latitude && location.longitude && location.accuracy) {
      return {
        latitude: location.latitude,
        longitude: location.longitude,
        accuracy: location.accuracy,
      };
    }
    return null;
  };

  return {
    ...location,
    getLocationContext,
  };
};