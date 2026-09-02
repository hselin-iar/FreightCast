export default async function handler(req, res) {
  const backendUrl = process.env.VITE_API_BASE_URL || 'https://freightcast.onrender.com';
  
  try {
    const response = await fetch(`${backendUrl}/health`);
    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`);
    }
    const data = await response.json();
    return res.status(200).json({ status: 'success', message: 'Backend kept alive', data });
  } catch (error) {
    return res.status(500).json({ status: 'error', message: error.message || 'Unknown error' });
  }
}
