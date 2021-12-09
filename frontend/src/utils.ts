export enum PageState {
  loading,
  success,
  error,
}

/**
 * Reads a file and returns base64 encoded file
 * @param file
 * @returns
 */
export const toBase64 = (file: File) =>
  new Promise<string | ArrayBuffer | null>((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result);
    reader.onerror = (error) => reject(error);
  });
