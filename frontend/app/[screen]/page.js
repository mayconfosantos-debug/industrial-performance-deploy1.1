import { Suspense } from 'react'
import DashboardClient from '../../components/DashboardClient'

function ScreenFallback() {
  return <div style={{padding:'24px',color:'#dce9f0',background:'#061420',minHeight:'100vh'}}>Carregando Industrial Performance…</div>
}

export default async function ScreenPage({ params }) {
  const { screen } = await params
  return (
    <Suspense fallback={<ScreenFallback />}>
      <DashboardClient screen={screen} />
    </Suspense>
  )
}
