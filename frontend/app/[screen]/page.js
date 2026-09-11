import DashboardClient from '../../components/DashboardClient'
export default async function ScreenPage({ params }) {
  const { screen } = await params
  return <DashboardClient screen={screen}/>
}
