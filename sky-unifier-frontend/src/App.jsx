// App.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Select from 'react-select';
import { motion } from 'framer-motion';
import { Telescope, AlertCircle, RefreshCw } from 'lucide-react';
import { Oval } from 'react-loader-spinner'; // Assuming react-loader-spinner is installed

const API_BASE = 'http://127.0.0.1:8000';

const customSelectStyles = {
  control: (provided) => ({
    ...provided,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    color: 'white',
    boxShadow: 'none',
    '&:hover': { borderColor: 'rgba(255, 255, 255, 0.3)' },
  }),
  menu: (provided) => ({
    ...provided,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    backdropFilter: 'blur(10px)',
  }),
  option: (provided, state) => ({
    ...provided,
    backgroundColor: state.isSelected ? 'rgba(59, 130, 246, 0.5)' : 'transparent',
    color: 'white',
    '&:hover': { backgroundColor: 'rgba(59, 130, 246, 0.3)' },
  }),
  multiValue: (provided) => ({
    ...provided,
    backgroundColor: 'rgba(59, 130, 246, 0.5)',
  }),
  multiValueLabel: (provided) => ({
    ...provided,
    color: 'white',
  }),
  placeholder: (provided) => ({
    ...provided,
    color: 'rgba(255, 255, 255, 0.5)',
  }),
  singleValue: (provided) => ({
    ...provided,
    color: 'white',
  }),
};

function App() {
  const [ra, setRa] = useState('');
  const [dec, setDec] = useState('');
  const [size, setSize] = useState('');
  const [stretch, setStretch] = useState('sqrt');
  const [surveyOptions, setSurveyOptions] = useState([]);
  const [selectedSurveys, setSelectedSurveys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [viewMode, setViewMode] = useState('overlaid'); // 'overlaid' or 'sidebyside'
  const [visibleLayers, setVisibleLayers] = useState({});

  useEffect(() => {
    fetchSurveys();
  }, []);

  const fetchSurveys = async () => {
    try {
      const res = await axios.get(`${API_BASE}/surveys`);
      // Assuming response.data is { categories: { cat1: ['sur1', 'sur2'], ... } }
      const categories = res.data.categories || res.data;
      const groupedOptions = Object.keys(categories).map((cat) => ({
        label: cat,
        options: categories[cat].map((sur) => ({ value: sur, label: sur })),
      }));
      setSurveyOptions(groupedOptions);
    } catch (err) {
      setError('Failed to fetch surveys');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResponse(null);
    setLoading(true);
    try {
      const body = {
        ra: parseFloat(ra),
        dec: parseFloat(dec),
        size_deg: parseFloat(size),
        surveys: selectedSurveys.map((s) => s.value),
        stretch,
      };
      const res = await axios.post(`${API_BASE}/render`, body);
      // console.log(res.data.layers.map((l) => ({ ...l, opacity: 50 })));
      // console.log(res.data)
      setResponse({...res.data, layers: res.data.layers.map((l) => ({ ...l, opacity: 100 }))});
      // Initialize visible layers all true
      const vis = {};
      res.data.layers.forEach((layer) => {
        vis[layer.survey] = true;
      });
      setVisibleLayers(vis);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error rendering sky map');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setRa('');
    setDec('');
    setSize('');
    setStretch('sqrt');
    setSelectedSurveys([]);
    setResponse(null);
    setError(null);
    setVisibleLayers({});
  };

  const toggleLayer = (survey) => {
    setVisibleLayers((prev) => ({ ...prev, [survey]: !prev[survey] }));
  };

  const handleLayerChange = (layer, value) => {
    console.log(layer, value);
    setResponse((prev) => ({
      ...prev,
      layers: prev.layers.map((l) =>
        l.id === layer.id ? { ...l, opacity: value } : l
      ),
    }));
  };


  console.log(response)

  return (
    <div className="min-h-screen bg-black text-white font-orbitron overflow-hidden relative">
      {/* Starfield Background */}
      <div className="absolute inset-0 bg-gradient-to-b from-black to-indigo-900 opacity-80"></div>
      <div className="absolute inset-0 pointer-events-none">
        {/* Simple CSS starfield */}
        <div className="stars"></div>
        <div className="stars2"></div>
        <div className="stars3"></div>
      </div>

      <header className="text-center py-6">
        <h1 className="text-3xl font-bold flex items-center justify-center gap-2">
          <Telescope className="text-blue-400" />
          Multi-Telescope Data Fusion (Sky Unifier)
          <Telescope className="text-blue-400" />
          {/* <Planet className="text-violet-400" /> */}
        </h1>
      </header>

      <main className=" mx-auto px-4 md:flex md:gap-6">
        {/* Control Panel */}
        <motion.div
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          className="md:w-1/3 mb-6 md:mb-0"
        >
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-lg p-6">
            <form onSubmit={handleSubmit}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <input
                  type="number"
                  placeholder="RA e.g. 10.6847"
                  value={ra}
                  onChange={(e) => setRa(e.target.value)}
                  className="bg-transparent border border-white/20 rounded p-2 focus:outline-none focus:border-blue-400 glow"
                  required
                />
                <input
                  type="number"
                  placeholder="DEC e.g. 41.2687"
                  value={dec}
                  onChange={(e) => setDec(e.target.value)}
                  className="bg-transparent border border-white/20 rounded p-2 focus:outline-none focus:border-blue-400 glow"
                  required
                />
                <input
                  type="number"
                  placeholder="Size (deg) e.g. 0.5"
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  className="bg-transparent border border-white/20 rounded p-2 focus:outline-none focus:border-blue-400 glow"
                  required
                />
                <select
                  value={stretch}
                   classNamePrefix="select"
                  onChange={(e) => setStretch(e.target.value)}
                  className="bg-transparent border border-white/20 rounded p-2 focus:outline-none focus:border-blue-400 glow"
                >
                  <option className='bg-black opacity-[0.5]' value="sqrt">sqrt</option>
                  <option className='bg-black opacity-[0.5]' value="log">log</option>
                  <option className='bg-black opacity-[0.5]' value="linear">linear</option>
                </select>
              </div>
              <div className="mb-4">
                <Select
                  isMulti
                  options={surveyOptions}
                  value={selectedSurveys}
                  onChange={setSelectedSurveys}
                  styles={customSelectStyles}
                  placeholder="Select Surveys"
                  classNamePrefix="select"
                  required
                />
              </div>
              <div className="flex gap-4">
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded flex-1 flex items-center justify-center gap-2 glow"
                >
                  Render Sky Map <Telescope size={18} />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  type="button"
                  onClick={handleReset}
                  className="bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded flex-1 flex items-center justify-center gap-2 glow"
                >
                  Reset <RefreshCw size={18} />
                </motion.button>
              </div>
            </form>
              <div className="mt-6">
                  <h3 className="text-xl mb-2">Layers</h3>
                  <div className="grid gap-4">
                    {response?.layers?.map((layer) => {

         

                      return  <div key={layer.survey} className="bg-black/50 p-4 rounded border border-white/10 flex items-center justify-between">
                        <div className='w-[65%]'>
                          <p className="font-bold">{layer.survey}</p>
                          <p className="text-sm">Intensity: {layer.min} - {layer.max}</p>
                          <input  type='range' min={0} max={100} value={layer.opacity}  onChange={(e) => handleLayerChange(layer, e.target.value)} className="w-full py-2" />
                        </div>
                        <label className="flex items-center gap-2">
                          Visible
                          <input
                            type="checkbox"
                            checked={visibleLayers[layer.survey]}
                            onChange={() => toggleLayer(layer.survey)}
                            className="accent-blue-400"
                          />
                        </label>
                      </div>
                    })}
                  </div>
                </div>
          </div>
        </motion.div>

        {/* Output Panel */}
        <motion.div
          initial={{ opacity: 0, x: 50 }}
          animate={{ opacity: 1, x: 0 }}
          className="md:w-2/3"
        >
          <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-lg p-6 h-[89vh]">
            {error && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="bg-red-900/50 border border-red-500 rounded p-4 mb-4 flex items-center gap-2 "
              >
                <AlertCircle className="text-red-400" />
                {error}
              </motion.div>
            )}

            <div className="mb-4 flex justify-center gap-4">
              <button
                onClick={() => setViewMode('overlaid')}
                className={`px-4 py-2 rounded ${viewMode === 'overlaid' ? 'bg-blue-600' : 'bg-gray-700'} glow`}
              >
                Overlaid
              </button>
              <button
                onClick={() => setViewMode('sidebyside')}
                className={`px-4 py-2 rounded ${viewMode === 'sidebyside' ? 'bg-blue-600' : 'bg-gray-700'} glow`}
              >
                Side by Side
              </button>
            </div>

            {loading ? (
              <div className="flex justify-center items-center h-auto ">
                <Oval color="#3B82F6" height={80} width={80} />
              </div>
            ) : response ? (
              <>
                <div className={`${viewMode === 'overlaid' ? 'relative ' : 'flex flex-wrap gap-4 overflow-y-scroll h-[79.5vh] '}`}>
                  {response?.layers
                    ?.filter((layer) => visibleLayers[layer?.survey])
                    ?.map((layer) => (
                      <div key={layer.survey} className={`${viewMode === 'overlaid' ? 'absolute inset-0 h-[79.5vh] w-full' : ''} ${response?.layers?.length > 2 ? "w-[48%] h-[48%]" : ""} `}>
                        <img
                          src={`${API_BASE}${layer.url}`}
                          alt={layer.survey}
                          className={`w-full h-full object-container ${viewMode === 'overlaid' ? ` mix-blend-screen` : ''} `}
                          style={viewMode === 'overlaid' ? { opacity: layer?.opacity / 100 } : {}}
                        />
                      </div>
                    ))}
                </div>
              
              </>
            ) : (
              <div className="text-center text-gray-400 h-64 flex items-center justify-center">
                Enter parameters and render to see the sky map.
              </div>
            )}
          </div>
        </motion.div>
      </main>
    </div>
  );
}

export default App;