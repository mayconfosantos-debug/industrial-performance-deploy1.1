export const API = process.env.NEXT_PUBLIC_API_URL || ''

export async function getJSON(path){
  const res = await fetch(`${API}${path}`, { cache:'no-store' })
  if(!res.ok) throw new Error(await res.text())
  return res.json()
}
